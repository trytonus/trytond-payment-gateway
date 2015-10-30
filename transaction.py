# -*- coding: utf-8 -*-
import re
from uuid import uuid4
from decimal import Decimal
from datetime import datetime
from sql.functions import Trim, Substring
from sql.operators import Concat

import yaml
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval, If, Bool
from trytond.wizard import Wizard, StateView, StateTransition, \
    Button, StateAction
from trytond.transaction import Transaction
from trytond.exceptions import UserError
from trytond.model import ModelSQL, ModelView, Workflow, fields
from trytond import backend


__all__ = [
    'PaymentGateway', 'PaymentTransaction',
    'TransactionLog', 'PaymentProfile', 'AddPaymentProfileView',
    'AddPaymentProfile', 'BaseCreditCardViewMixin', 'Party',
    'TransactionUseCardView', 'TransactionUseCard', 'PaymentGatewayResUser',
    'User', 'AccountMove', 'CreateRefund'
]
__metaclass__ = PoolMeta

READONLY_IF_NOT_DRAFT = {'readonly': Eval('state') != 'draft'}
STATES = {
    'readonly': ~Eval('active', True),
}
DEPENDS = ['active']


class PaymentGateway(ModelSQL, ModelView):
    """
    Payment Gateway

    Payment gateway record is a specific configuration for a `provider`
    """
    __name__ = 'payment_gateway.gateway'

    active = fields.Boolean('Active', select=True)
    name = fields.Char(
        'Name', required=True, select=True, states=STATES, depends=DEPENDS
    )
    journal = fields.Many2One(
        'account.journal', 'Journal', required=True,
        states=STATES, depends=DEPENDS
    )
    provider = fields.Selection(
        'get_providers', 'Provider', required=True,
        states=STATES, depends=DEPENDS
    )
    method = fields.Selection(
        'get_methods', 'Method', required=True, states=STATES, depends=DEPENDS
    )
    test = fields.Boolean('Test Account', states=STATES, depends=DEPENDS)

    users = fields.Many2Many(
        'payment_gateway.gateway-res.user', 'payment_gateway', 'user', 'Users'
    )
    configured = fields.Boolean('Configured ?', readonly=True)

    @classmethod
    def __setup__(cls):
        super(PaymentGateway, cls).__setup__()
        cls._buttons.update({
            'test_gateway_configuration': {
                'readonly': ~Bool(Eval('active')),
            },
        })

    @classmethod
    @ModelView.button
    def test_gateway_configuration(cls, gateways):
        for gateway in gateways:
            journal = gateway.journal
            configured = bool(
                journal.debit_account and
                not journal.debit_account.party_required
            )
            gateway.configured = configured
            gateway.save()

    @staticmethod
    def default_active():
        return True

    @staticmethod
    def default_provider():
        return 'self'

    @classmethod
    def get_providers(cls):
        """
        Downstream modules can add to the list
        """
        return []

    @fields.depends('provider')
    def get_methods(self):
        """
        Downstream modules can override the method and add entries to this
        """
        return []


class PaymentTransaction(Workflow, ModelSQL, ModelView):
    '''Gateway Transaction'''
    __name__ = 'payment_gateway.transaction'

    uuid = fields.Char('UUID', required=True, readonly=True)
    description = fields.Char(
        'Description', states=READONLY_IF_NOT_DRAFT,
        depends=['state']
    )
    type = fields.Selection(
        [
            ('charge', 'Charge'),
            ('refund', 'Refund'),
        ], 'Type', required=True, select=True,
    )
    origin = fields.Reference(
        'Origin', selection='get_origin', select=True,
        states=READONLY_IF_NOT_DRAFT,
        depends=['state']
    )
    provider_reference = fields.Char(
        'Provider Reference', readonly=True, states={
            'invisible': Eval('state') == 'draft'
        }, depends=['state']
    )
    date = fields.Date(
        'Date', required=True,
        states=READONLY_IF_NOT_DRAFT,
        depends=['state']
    )
    company = fields.Many2One(
        'company.company', 'Company', required=True,
        states=READONLY_IF_NOT_DRAFT, select=True,
        domain=[
            ('id', If(Eval('context', {}).contains('company'), '=', '!='),
                Eval('context', {}).get('company', -1)),
        ], depends=['state']
    )
    party = fields.Many2One(
        'party.party', 'Party', required=True, ondelete='RESTRICT',
        depends=['state'], states=READONLY_IF_NOT_DRAFT,
    )
    payment_profile = fields.Many2One(
        'party.payment_profile', 'Payment Profile',
        domain=[
            ('party', '=', Eval('party')),
            ('gateway', '=', Eval('gateway')),
        ],
        ondelete='RESTRICT', depends=['state', 'party', 'gateway'],
        states=READONLY_IF_NOT_DRAFT,
    )
    address = fields.Many2One(
        'party.address', 'Address', required=True,
        domain=[('party', '=', Eval('party'))],
        depends=['state', 'party'], states=READONLY_IF_NOT_DRAFT,
        ondelete='RESTRICT'
    )
    amount = fields.Numeric(
        'Amount', digits=(16, Eval('currency_digits', 2)),
        required=True, depends=['state', 'currency_digits'],
        states=READONLY_IF_NOT_DRAFT,
    )
    currency = fields.Many2One(
        'currency.currency', 'Currency',
        required=True,
        depends=['state'], states=READONLY_IF_NOT_DRAFT,
    )
    currency_digits = fields.Function(
        fields.Integer('Currency Digits'),
        'on_change_with_currency_digits'
    )
    gateway = fields.Many2One(
        'payment_gateway.gateway', 'Gateway', required=True,
        states=READONLY_IF_NOT_DRAFT, depends=['state'], ondelete='RESTRICT',
    )
    provider = fields.Function(
        fields.Char('Provider'), 'get_provider'
    )
    method = fields.Function(
        fields.Char('Payment Gateway Method'), 'get_method'
    )
    move = fields.Many2One(
        'account.move', 'Move', readonly=True, ondelete='RESTRICT'
    )
    logs = fields.One2Many(
        'payment_gateway.transaction.log', 'transaction',
        'Logs', depends=['state'], states={
            'readonly': Eval('state') in ('done', 'cancel')
        }
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('in-progress', 'In Progress'),
        ('failed', 'Failed'),
        ('authorized', 'Authorized'),
        ('completed', 'Completed'),
        ('posted', 'Posted'),
        ('cancel', 'Canceled'),
    ], 'State', readonly=True)
    shipping_address = fields.Function(
        fields.Many2One('party.address', 'Shipping Address'),
        'get_shipping_address'
    )
    credit_account = fields.Many2One(
        'account.account', 'Credit Account',
        states=READONLY_IF_NOT_DRAFT, depends=['state'],
        required=True, select=True
    )
    last_four_digits = fields.Char('Last Four Digits')

    @staticmethod
    def default_type():
        return 'charge'

    def get_rec_name(self, name=None):
        """
        Return the most meaningful rec_name
        """
        if self.state == 'draft':
            return self.uuid
        if not self.payment_profile:
            return '%s/%s' % (self.gateway.name, self.provider_reference)
        return '%s/%s' % (
            self.payment_profile.rec_name, self.provider_reference
        )

    @classmethod
    def _get_origin(cls):
        'Return list of Model names for origin Reference'
        return ['payment_gateway.transaction']

    @classmethod
    def get_origin(cls):
        IrModel = Pool().get('ir.model')
        models = cls._get_origin()
        models = IrModel.search([('model', 'in', models)])
        return [(None, '')] + [(m.model, m.name) for m in models]

    @classmethod
    def __setup__(cls):
        super(PaymentTransaction, cls).__setup__()
        cls._order.insert(0, ('date', 'DESC'))

        cls._error_messages.update({
            'feature_not_available': 'The feature %s is not avaialable '
                                     'for provider %s',
            'process_only_manual': 'Only manual process can be processed.',
        })
        cls._transitions |= set((
            ('draft', 'in-progress'),
            ('draft', 'authorized'),
            ('draft', 'completed'),     # manual payments
            ('in-progress', 'failed'),
            ('in-progress', 'authorized'),
            ('in-progress', 'completed'),
            ('in-progress', 'cancel'),
            ('authorized', 'cancel'),
            ('authorized', 'completed'),
            ('completed', 'posted'),
        ))
        cls._buttons.update({
            'process': {
                'invisible': ~(
                    (Eval('state') == 'draft') &
                    (Eval('method') == 'manual') &
                    (Eval('type') == 'charge')
                ),
            },
            'cancel': {
                'invisible': ~Eval('state').in_(['in-progress', 'authorized']),
            },
            'authorize': {
                'invisible': ~(
                    (Eval('state') == 'draft') &
                    Eval('payment_profile', True) &
                    (Eval('method') == 'credit_card') &
                    (Eval('type') == 'charge')
                ),
            },
            'settle': {
                'invisible': ~(
                    (Eval('state') == 'authorized') &
                    (Eval('method') == 'credit_card') &
                    (Eval('type') == 'charge')
                ),
            },
            'retry': {
                'invisible': ~(
                    (Eval('state') == 'failed') &
                    (Eval('type') == 'charge')
                )
            },
            'capture': {
                'invisible': ~(
                    (Eval('state') == 'draft') &
                    Eval('payment_profile', True) &
                    (Eval('method') == 'credit_card') &
                    (Eval('type') == 'charge')
                ),
            },
            'post': {
                'invisible': ~(
                    (Eval('state') == 'completed') &
                    (Eval('type') == 'charge')
                )
            },
            'use_card': {
                'invisible': ~(
                    (Eval('state') == 'draft') &
                    ~Bool(Eval('payment_profile')) &
                    (Eval('method') == 'credit_card')
                ),
            },
            'update_status': {
                'invisible': ~Eval('state').in_(['in-progress'])
            },
            'refund': {
                'invisible': ~(
                    (Eval('type') == 'refund') &
                    (Eval('state') == 'draft')
                )
            }
        })

        cls.credit_account.domain = [
            ('company', '=', Eval('company', -1)),
            ('kind', 'in', cls._credit_account_domain())
        ]
        cls.credit_account.depends += ['company']

    @classmethod
    def __register__(cls, module_name):
        Party = Pool().get('party.party')
        Model = Pool().get('ir.model')
        ModelField = Pool().get('ir.model.field')
        Property = Pool().get('ir.property')
        PaymentProfile = Pool().get('party.payment_profile')
        TableHandler = backend.get('TableHandler')
        cursor = Transaction().cursor
        table = TableHandler(cursor, cls, module_name)

        migration_needed = False
        if not table.column_exist('credit_account'):
            migration_needed = True

        migrate_last_four_digits = False
        if not table.column_exist('last_four_digits'):
            migrate_last_four_digits = True

        super(PaymentTransaction, cls).__register__(module_name)

        if migration_needed and not Pool.test:
            # Migration
            # Set party's receivable account as the credit_account on
            # transactions
            transaction = cls.__table__()
            party = Party.__table__()
            property = Property.__table__()

            account_model, = Model.search([
                ('model', '=', 'party.party'),
            ])
            account_receivable_field, = ModelField.search([
                ('model', '=', account_model.id),
                ('name', '=', 'account_receivable'),
                ('ttype', '=', 'many2one'),
            ])

            update = transaction.update(
                columns=[transaction.credit_account],
                values=[
                    Trim(
                        Substring(property.value, ',.*'), 'LEADING', ','
                    ).cast(cls.credit_account.sql_type().base)
                ],
                from_=[party, property],
                where=(
                    transaction.party == party.id
                ) & (
                    property.res == Concat(Party.__name__ + ',', party.id)
                ) & (
                    property.field == account_receivable_field.id
                ) & (
                    property.company == transaction.company
                )

            )
            cursor.execute(*update)

        if migrate_last_four_digits and not Pool.test:
            transaction = cls.__table__()
            payment_profile = PaymentProfile.__table__()
            cursor.execute(*transaction.update(
                columns=[transaction.last_four_digits],
                values=[payment_profile.last_4_digits],
                from_=[payment_profile],
                where=(transaction.payment_profile == payment_profile.id)
            ))

    @classmethod
    def _credit_account_domain(cls):
        """
        Return a list of account kind
        """
        return ['receivable']

    @staticmethod
    def default_uuid():
        return unicode(uuid4())

    @staticmethod
    def default_date():
        Date = Pool().get('ir.date')
        return Date.today()

    @staticmethod
    def default_company():
        return Transaction().context.get('company')

    @staticmethod
    def default_currency():
        Company = Pool().get('company.company')
        if Transaction().context.get('company'):
            company = Company(Transaction().context['company'])
            return company.currency.id

    @staticmethod
    def default_state():
        return 'draft'

    @classmethod
    def copy(cls, records, default=None):
        if default is None:
            default = {}
        default.update({
            'uuid': cls.default_uuid(),
            'provider_reference': None,
            'move': None,
            'logs': None,
            'state': 'draft',
        })
        return super(PaymentTransaction, cls).copy(records, default)

    @fields.depends('currency')
    def on_change_with_currency_digits(self, name=None):
        if self.currency:
            return self.currency.digits
        return 2

    @fields.depends('party')
    def on_change_party(self):
        res = {
            'address': None,
            'credit_account': None,
        }
        if self.party:
            res['credit_account'] = self.party.account_receivable and \
                    self.party.account_receivable.id
            try:
                address = self.party.address_get(type='invoice')
            except AttributeError:
                # account_invoice module is not installed
                pass
            else:
                res['address'] = address.id
                res['address.rec_name'] = address.rec_name
        return res

    @fields.depends('payment_profile')
    def on_change_payment_profile(self):
        res = {}
        if self.payment_profile:
            res['address'] = self.payment_profile.address.id
            res['address.rec_name'] = self.payment_profile.address.rec_name
        return res

    def get_provider(self, name=None):
        """
        Return the gateway provider based on the gateway
        """
        return self.gateway.provider

    def get_method(self, name=None):
        """
        Return the method based on the gateway
        """
        return self.gateway.method

    @fields.depends('gateway')
    def on_change_gateway(self):
        if self.gateway:
            return {
                'provider': self.gateway.provider,
                'method': self.gateway.method,
            }
        return {}

    def on_change_with_provider(self):
        return self.get_provider()

    def cancel_self(self):
        """
        Method to cancel the given payment.
        """
        if self.method == 'manual' and \
                self.state in ('in-progress', 'authorized'):
            return True
        self.raise_user_error(
            'Cannot cancel self payments which are not manual and in-progress'
        )

    @classmethod
    @ModelView.button
    @Workflow.transition('cancel')
    def cancel(cls, transactions):
        for transaction in transactions:
            if transaction.type == 'refund':
                continue

            method_name = 'cancel_%s' % transaction.gateway.provider
            if not hasattr(transaction, method_name):
                cls.raise_user_error(
                    'feature_not_available',
                    ('cancellation', transaction.gateway.provider),
                )
            getattr(transaction, method_name)()

    @classmethod
    @ModelView.button
    @Workflow.transition('in-progress')
    def authorize(cls, transactions):
        for transaction in transactions:
            method_name = 'authorize_%s' % transaction.gateway.provider
            if not hasattr(transaction, method_name):
                cls.raise_user_error(
                    'feature_not_available',
                    ('authorization', transaction.gateway.provider),
                )
            getattr(transaction, method_name)()

    @classmethod
    @ModelView.button
    @Workflow.transition('completed')
    def process(cls, transactions):
        """
        Process a given transaction.

        Used only for gateways which have manual/offline method - like cash,
        cheque, external payment etc.
        """
        for transaction in transactions:
            if transaction.method != 'manual':
                cls.raise_user_error('process_only_manual')
        pass

    @classmethod
    @ModelView.button
    @Workflow.transition('in-progress')
    def retry(cls, transactions):
        for transaction in transactions:
            method_name = 'retry_%s' % transaction.gateway.provider
            if not hasattr(transaction, method_name):
                cls.raise_user_error(
                    'feature_not_available',
                    ('retry', transaction.gateway.provider)
                )
            getattr(transaction, method_name)()

    @classmethod
    @ModelView.button
    @Workflow.transition('completed')
    def settle(cls, transactions):
        for transaction in transactions:
            method_name = 'settle_%s' % transaction.gateway.provider
            if not hasattr(transaction, method_name):
                cls.raise_user_error(
                    'feature_not_available',
                    ('settle', transaction.gateway.provider)
                )
            getattr(transaction, method_name)()

    @classmethod
    @ModelView.button
    @Workflow.transition('in-progress')
    def capture(cls, transactions):
        for transaction in transactions:
            method_name = 'capture_%s' % transaction.gateway.provider
            if not hasattr(transaction, method_name):
                cls.raise_user_error(
                    'feature_not_available',
                    ('capture', transaction.gateway.provider)
                )
            getattr(transaction, method_name)()

    @classmethod
    @ModelView.button
    @Workflow.transition('posted')
    def post(cls, transactions):
        """
        Complete the transactions by creating account moves and post them.

        This method is likely to end in failure if the initial configuration
        of the journal and fiscal periods have not been done. You could
        alternatively use the safe_post instance method to try to post the
        record, but ignore the error silently.
        """
        for transaction in transactions:
            if not transaction.move:
                transaction.create_move()

    @classmethod
    @ModelView.button
    def refund(cls, transactions):
        for transaction in transactions:
            assert transaction.type == 'refund', \
                "Transaction type must be refund"
            method_name = 'refund_%s' % transaction.gateway.provider
            if not hasattr(transaction, method_name):
                cls.raise_user_error(
                    'feature_not_available',
                    ('refund', transaction.gateway.provider)
                )
            getattr(transaction, method_name)()

    @classmethod
    @ModelView.button
    def update_status(cls, transactions):
        """
        Check the status with the payment gateway provider and update the
        status of this transaction accordingly.
        """
        for transaction in transactions:
            method_name = 'update_%s' % transaction.gateway.provider
            if not hasattr(transaction, method_name):
                cls.raise_user_error(
                    'feature_not_available'
                    ('update status', transaction.gateway.provider)
                )
            getattr(transaction, method_name)()

    def safe_post(self):
        """
        If the initial configuration including defining a period and
        journal is not completed, marking as done could fail. In
        such cases, just mark as in-progress and let the user to
        manually mark as done.

        Failing  would otherwise rollback transaction but its
        not possible to rollback the payment
        """
        try:
            self.post([self])
        except UserError, exc:
            log = 'Could not mark as done\n'
            log += unicode(exc)

            # Delete the account move if there's one
            # We need to do this because if we post transactions
            # asyncronously using workers, the unwanted move will be
            # commited causing duplicate moves
            move_exists, move_number = self.delete_move_if_exists()
            if move_exists:
                log += "\nDeleted account move #%s" % move_number

            TransactionLog.create([{
                'transaction': self,
                'log': log
            }])

    def delete_move_if_exists(self):
        """
        Delete the account move if there's one
        """
        Move = Pool().get('account.move')

        move = Move.search([
            ('origin', '=', '%s,%d' % (self.__name__, self.id)),
            ('lines.party', '=', self.party.id),
        ], limit=1)

        if move:
            number = move[0].number
            Move.delete([move[0]])
            return True, number
        return False, None

    def create_move(self, date=None):
        """
        Create the account move for the payment

        :param date: Optional date for the account move
        :return: Active record of the created move
        """
        Currency = Pool().get('currency.currency')
        Period = Pool().get('account.period')
        Move = Pool().get('account.move')

        journal = self.gateway.journal
        date = date or self.date

        if not journal.debit_account:
            self.raise_user_error('missing_debit_account', (journal.rec_name,))

        period_id = Period.find(self.company.id, date=date)

        amount_second_currency = second_currency = None
        amount = self.amount

        if self.currency != self.company.currency:
            amount = Currency.compute(
                self.currency, self.amount, self.company.currency
            )
            amount_second_currency = self.amount
            second_currency = self.currency

        refund = self.type == 'refund'
        lines = [{
            'description': self.rec_name,
            'account': self.credit_account.id,
            'party': self.party.id,
            'debit': Decimal('0.0') if not refund else amount,
            'credit': Decimal('0.0') if refund else amount,
            'amount_second_currency': amount_second_currency,
            'second_currency': second_currency,
        }, {
            'description': self.rec_name,
            'account': journal.debit_account.id,
            'debit': Decimal('0.0') if refund else amount,
            'credit': Decimal('0.0') if not refund else amount,
            'amount_second_currency': amount_second_currency,
            'second_currency': second_currency,
        }]

        move, = Move.create([{
            'journal': journal.id,
            'period': period_id,
            'date': date,
            'lines': [('create', lines)],
            'origin': '%s,%d' % (self.__name__, self.id),
        }])
        Move.post([move])

        # Set the move as the move of this transaction
        self.move = move
        self.save()

        return move

    @classmethod
    @ModelView.button_action('payment_gateway.wizard_transaction_use_card')
    def use_card(cls, transactions):
        pass

    def get_shipping_address(self, name):
        """
        Returns the shipping address for the transaction.

        The downstream modules can override this to send the
        appropriate address in transaction.
        """
        return None

    def create_refund(self, amount=None):
        assert self.type == 'charge', "Transaction type must be charge"

        refund_transaction, = self.copy([self])

        refund_transaction.type = 'refund'
        refund_transaction.amount = amount or self.amount
        refund_transaction.origin = self
        refund_transaction.save()

        return refund_transaction


class TransactionLog(ModelSQL, ModelView):
    "Transaction Log"
    __name__ = 'payment_gateway.transaction.log'

    timestamp = fields.DateTime('Event Timestamp', readonly=True)
    transaction = fields.Many2One(
        'payment_gateway.transaction', 'Transaction',
        required=True, readonly=True,
    )
    is_system_generated = fields.Boolean('Is System Generated')
    log = fields.Text(
        'Log', required=True, depends=['is_system_generated'],
        states={'readonly': Eval('is_system_generated', True)}
    )

    @staticmethod
    def default_is_system_generated():
        return False

    @staticmethod
    def default_timestamp():
        return datetime.utcnow()

    @classmethod
    def serialize_and_create(cls, transaction, data):
        """
        Serialise a given object and then save it as a log

        :param transaction: The transaction against which the log needs to be
                            saved
        :param data: The data object that needs to be saved
        """
        return cls.create([{
            'transaction': transaction,
            'log': yaml.dump(data, default_flow_style=False),
        }])[0]


WHEN_CP = {
    # Required if card is present
    'required': Bool(Eval('card_present')),

    # Readonly if card is **not** present
    'readonly': ~Bool(Eval('card_present'))
}
WHEN_CNP = {
    # Required if card is not present
    'required': ~Bool(Eval('card_present')),

    # Readonly if card is present
    'readonly': Bool(Eval('card_present'))
}


class BaseCreditCardViewMixin(object):
    """
    A Reusable Mixin class to get Credit Card view
    """
    card_present = fields.Boolean(
        'Card is Present',
        help="If the card is present and the card can be swiped"
    )
    swipe_data = fields.Char(
        'Swipe Card',
        states=WHEN_CP, depends=['card_present'],
    )
    owner = fields.Char(
        'Card Owner',
        states=WHEN_CNP, depends=['card_present'],
    )
    number = fields.Char(
        'Card Number',
        states=WHEN_CNP, depends=['card_present'],
    )
    expiry_month = fields.Selection(
        [
            ('01', '01-January'),
            ('02', '02-February'),
            ('03', '03-March'),
            ('04', '04-April'),
            ('05', '05-May'),
            ('06', '06-June'),
            ('07', '07-July'),
            ('08', '08-August'),
            ('09', '09-September'),
            ('10', '10-October'),
            ('11', '11-November'),
            ('12', '12-December'),
        ], 'Expiry Month',
        states=WHEN_CNP, depends=['card_present'],
    )
    expiry_year = fields.Char(
        'Expiry Year', size=4,
        states=WHEN_CNP, depends=['card_present'],
    )
    csc = fields.Char(
        'Card Security Code (CVV/CVD)', size=4, states=WHEN_CNP,
        depends=['card_present'], help='CVD/CVV/CVN'
    )

    @staticmethod
    def default_owner():
        """
        If a party is provided in the context fill up this instantly
        """
        Party = Pool().get('party.party')

        party_id = Transaction().context.get('party')
        if party_id:
            return Party(party_id).name

    track1_re = re.compile(
        r'^%(?P<FC>\w)(?P<PAN>\d+)\^(?P<NAME>.{2,26})\^(?P<YY>\d{2})'
        '(?P<MM>\d{2})(?P<SC>\d{0,3}|\^)(?P<DD>.*)\?$'
    )

    @fields.depends('swipe_data')
    def on_change_swipe_data(self):
        """
        Try to parse the track1 and track2 data into Credit card information
        """
        res = {}

        try:
            track1, track2 = self.swipe_data.split(';')
        except ValueError:
            return {
                'owner': '',
                'number': '',
                'expiry_month': '',
                'expiry_year': '',
            }

        match = self.track1_re.match(track1)
        if match:
            # Track1 matched, extract info and send
            assert match.group('FC').upper() == 'B', 'Unknown card Format Code'

            res['owner'] = match.group('NAME')
            res['number'] = match.group('PAN')
            res['expiry_month'] = match.group('MM')
            res['expiry_year'] = '20' + match.group('YY')

        # TODO: Match track 2
        return res


class Party:
    __name__ = 'party.party'

    payment_profiles = fields.One2Many(
        'party.payment_profile', 'party', 'Payment Profiles'
    )
    default_payment_profile = fields.Function(
        fields.Many2One('party.payment_profile', 'Default Payment Profile'),
        'get_default_payment_profile'
    )

    @classmethod
    def __setup__(cls):
        super(Party, cls).__setup__()
        cls._buttons.update({
            'add_payment_profile': {}
        })

    @classmethod
    @ModelView.button_action('payment_gateway.wizard_add_payment_profile')
    def add_payment_profile(cls, parties):
        pass

    def get_default_payment_profile(self, name):
        """
        Gets the payment profile with the lowest sequence,
        as in 1 is the highest priority and sets it
        """
        return self.payment_profiles and self.payment_profiles[0].id or None


class PaymentProfile(ModelSQL, ModelView):
    """
    Secure Payment Profile

    Several payment gateway service providers offer a secure way to store
    confidential customer credit card insformation on their server.
    Transactions can then be processed against these profiles without the need
    to recollect payment information from the customer, and without the need
    to store confidential credit card information in Tryton.

    This model represents a profile thus stored with any of the third party
    providers.
    """
    __name__ = 'party.payment_profile'

    sequence = fields.Integer('Sequence', required=True)
    party = fields.Many2One('party.party', 'Party', required=True)
    address = fields.Many2One(
        'party.address', 'Address', required=True,
        domain=[('party', '=', Eval('party'))], depends=['party']
    )
    gateway = fields.Many2One(
        'payment_gateway.gateway', 'Gateway', required=True,
        ondelete='RESTRICT', readonly=True,
    )
    provider_reference = fields.Char(
        'Provider Reference', required=True, readonly=True
    )
    last_4_digits = fields.Char('Last 4 digits', readonly=True)
    expiry_month = fields.Selection([
        ('01', '01-January'),
        ('02', '02-February'),
        ('03', '03-March'),
        ('04', '04-April'),
        ('05', '05-May'),
        ('06', '06-June'),
        ('07', '07-July'),
        ('08', '08-August'),
        ('09', '09-September'),
        ('10', '10-October'),
        ('11', '11-November'),
        ('12', '12-December'),
    ], 'Expiry Month', required=True, readonly=True)
    expiry_year = fields.Char(
        'Expiry Year', required=True, size=4, readonly=True
    )
    active = fields.Boolean('Active', select=True)

    @staticmethod
    def default_sequence():
        return 10

    @classmethod
    def __setup__(cls):
        super(PaymentProfile, cls).__setup__()
        cls._order.insert(0, ('sequence', 'ASC'))

    def get_rec_name(self, name=None):
        if self.last_4_digits:
            return self.gateway.name + ' ' + ('xxxx ' * 3) + self.last_4_digits
        return 'Incomplete Card'

    @staticmethod
    def default_active():
        return True


class AddPaymentProfileView(BaseCreditCardViewMixin, ModelView):
    """
    View for adding a payment profile
    """
    __name__ = 'party.payment_profile.add_view'

    party = fields.Many2One(
        'party.party', 'Party', required=True,
        states={'invisible': Eval('party_invisible', False)}
    )
    address = fields.Many2One(
        'party.address', 'Address', required=True,
        domain=[('party', '=', Eval('party'))],
        depends=['party']
    )
    provider = fields.Selection('get_providers', 'Provider', required=True)
    gateway = fields.Many2One(
        'payment_gateway.gateway', 'Gateway', required=True,
        domain=[('provider', '=', Eval('provider'))],
        depends=['provider']
    )

    @classmethod
    def get_providers(cls):
        """
        Return the list of providers who support credit card profiles.
        """
        return []


class AddPaymentProfile(Wizard):
    """
    Add a payment profile
    """
    __name__ = 'party.party.payment_profile.add'

    start_state = 'card_info'

    card_info = StateView(
        'party.payment_profile.add_view',
        'payment_gateway.payment_profile_add_view_form',
        [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Add', 'add', 'tryton-ok', default=True)
        ]
    )
    add = StateTransition()

    def default_card_info(self, fields):
        Party = Pool().get('party.party')

        party = Party(Transaction().context.get('active_id'))

        res = {
                'party': party.id,
                'owner': party.name,
        }

        try:
            address = self.party.address_get(type='invoice')
        except AttributeError:
            # account_invoice module is not installed
            pass
        else:
            res['address'] = address.id

        return res

    def create_profile(self, provider_reference, **kwargs):
        """
        A helper function that creates a profile from the card information
        that was entered into the View of the wizard. This helper could be
        called by the method which implement the API and wants to create the
        profile with provider_reference.

        :param provider_reference: Value for the provider_reference field.
        :return: Active record of the created profile
        """
        Profile = Pool().get('party.payment_profile')

        profile = Profile(
            party=self.card_info.party.id,
            address=self.card_info.address.id,
            gateway=self.card_info.gateway.id,
            last_4_digits=self.card_info.number[-4:],
            expiry_month=self.card_info.expiry_month,
            expiry_year=self.card_info.expiry_year,
            provider_reference=provider_reference,
            **kwargs
        )
        profile.save()

        # Wizard session data is stored in database
        # Make sure credit card info does not hit the database
        self.card_info.number = None
        self.card_info.csc = None
        return profile

    def transition_add(self):
        """
        Downstream module implementing the functionality should check for the
        provider type and handle it accordingly.

        To handle, name your method transition_add_<provider_name>. For example
        if your proivder internal name is paypal, then the method name
        should be `transition_add_paypal`

        Once validated, the payment profile must be created by the method and
        the active record of the created payment record should be returned.

        A helper function is provided in this class itself which fills in most
        of the information automatically and the only additional information
        required is the reference from the payment provider.

        If return_profile is set to True in the context, then the created
        profile is returned.
        """
        method_name = 'transition_add_%s' % self.card_info.provider
        if Transaction().context.get('return_profile'):
            return getattr(self, method_name)()
        else:
            getattr(self, method_name)()
            return 'end'


class TransactionUseCardView(BaseCreditCardViewMixin, ModelView):
    """
    View for putting in credit card information
    """
    __name__ = 'payment_gateway.transaction.use_card.view'


class TransactionUseCard(Wizard):
    """
    Transaction using Credit Card wizard
    """
    __name__ = 'payment_gateway.transaction.use_card'

    start_state = 'card_info'

    card_info = StateView(
        'payment_gateway.transaction.use_card.view',
        'payment_gateway.transaction_use_card_view_form',
        [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Authorize', 'authorize', 'tryton-go-next'),
            Button('Capture', 'capture', 'tryton-ok', default=True),
        ]
    )
    capture = StateTransition()
    authorize = StateTransition()

    def transition_capture(self):
        """
        Delegates to the capture method for the provider in
        payment_gateway.transaction
        """
        PaymentTransaction = Pool().get('payment_gateway.transaction')

        transaction = PaymentTransaction(
            Transaction().context.get('active_id')
        )

        getattr(transaction, 'capture_%s' % transaction.gateway.provider)(
            self.card_info
        )

        self.clear_cc_info()
        return 'end'

    def transition_authorize(self):
        """
        Delegates to the authorize method for the provider in
        payment_gateway.transaction
        """
        PaymentTransaction = Pool().get('payment_gateway.transaction')

        transaction = PaymentTransaction(
            Transaction().context.get('active_id')
        )

        getattr(transaction, 'authorize_%s' % transaction.gateway.provider)(
            self.card_info
        )

        self.clear_cc_info()
        return 'end'

    def clear_cc_info(self):
        """
        Tryton stores Wizard session data while it's execution
        We need to make sure credit card info does not hit the database
        """
        self.card_info.number = None
        self.card_info.csc = None


class User:
    __name__ = 'res.user'

    payment_gateways = fields.Many2Many(
        'payment_gateway.gateway-res.user', 'user', 'payment_gateway',
        'Payment Gateways'
    )


class PaymentGatewayResUser(ModelSQL):
    'Payment Gateway - Res User'
    __name__ = 'payment_gateway.gateway-res.user'
    _table = 'payment_gateway_gateway_res_user'

    payment_gateway = fields.Many2One(
        'payment_gateway.gateway', 'Payment Gateway', ondelete='CASCADE',
        select=True, required=True
    )
    user = fields.Many2One(
        'res.user', 'User', ondelete='RESTRICT', required=True
    )


class AccountMove:
    __name__ = 'account.move'

    @classmethod
    def _get_origin(cls):
        res = super(AccountMove, cls)._get_origin()

        if 'payment_gateway.transaction' not in res:
            res.append('payment_gateway.transaction')
        return res


class CreateRefund(Wizard):
    "Create Refund"
    __name__ = "payment_gateway.transaction.create_refund"
    start_state = 'open'

    open = StateAction('payment_gateway.act_transaction')

    def do_open(self, action):
        GatewayTransaction = Pool().get('payment_gateway.transaction')

        transactions = GatewayTransaction.browse(
            Transaction().context['active_ids']
        )

        refund_transactions = []
        for transaction in transactions:
            refund_transactions.append(transaction.create_refund())

        data = {'res_id': map(int, refund_transactions)}
        return action, data

    def transition_open(self):
        return 'end'
