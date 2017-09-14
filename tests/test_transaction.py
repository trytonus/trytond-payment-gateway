# -*- coding: utf-8 -*-
import unittest
import datetime
from dateutil.relativedelta import relativedelta

from trytond.tests.test_tryton import (
    USER, CONTEXT, POOL, ModuleTestCase, with_transaction
)
import trytond.tests.test_tryton
from trytond.transaction import Transaction
from trytond.exceptions import UserError


class TestTransaction(ModuleTestCase):
    """
    Test transaction
    """

    module = 'payment_gateway'

    def setUp(self):
        """
        Set up data used in the tests.
        """

        self.Currency = POOL.get('currency.currency')
        self.Company = POOL.get('company.company')
        self.Party = POOL.get('party.party')
        self.User = POOL.get('res.user')
        self.Journal = POOL.get('account.journal')
        self.PaymentGateway = POOL.get('payment_gateway.gateway')
        self.PaymentGatewayTransaction = POOL.get('payment_gateway.transaction')
        self.AccountMove = POOL.get('account.move')

    def _create_fiscal_year(self, date=None, company=None):
        """
        Creates a fiscal year and requried sequences
        """
        FiscalYear = POOL.get('account.fiscalyear')
        Sequence = POOL.get('ir.sequence')
        Company = POOL.get('company.company')

        if date is None:
            date = datetime.date.today()

        if company is None:
            company, = Company.search([], limit=1)

        fiscal_year, = FiscalYear.create([{
            'name': '%s' % date.year,
            'start_date': date + relativedelta(month=1, day=1),
            'end_date': date + relativedelta(month=12, day=31),
            'company': company,
            'post_move_sequence': Sequence.create([{
                'name': '%s' % date.year,
                'code': 'account.move',
                'company': company,
            }])[0],
        }])
        FiscalYear.create_period([fiscal_year])
        return fiscal_year

    def _create_coa_minimal(self, company):
        """Create a minimal chart of accounts
        """
        AccountTemplate = POOL.get('account.account.template')
        Account = POOL.get('account.account')

        account_create_chart = POOL.get(
            'account.create_chart', type="wizard")

        account_template = AccountTemplate.search(
            [('parent', '=', None)]
        )[0]

        session_id, _, _ = account_create_chart.create()
        create_chart = account_create_chart(session_id)
        create_chart.account.account_template = account_template
        create_chart.account.company = company
        create_chart.transition_create_account()

        receivable, = Account.search([
            ('kind', '=', 'receivable'),
            ('company', '=', company),
        ])
        payable, = Account.search([
            ('kind', '=', 'payable'),
            ('company', '=', company),
        ])
        create_chart.properties.company = company
        create_chart.properties.account_receivable = receivable
        create_chart.properties.account_payable = payable
        create_chart.transition_create_properties()

    @with_transaction()
    def test_payment_transaction_search_rec_name(self):
        """
        Search payment transaction with UUID and Customer Name
        """
        self.setup_defaults()

        gateway, = self.PaymentGateway.create([{
            'name': 'Test Gateway',
            'journal': self.cash_journal.id,
            'provider': 'self',
            'method': 'manual',
        }])

        with Transaction().set_context(company=self.company.id):
            transaction, = self.PaymentGatewayTransaction.create([{
                'party': self.party.id,
                'credit_account': self.party.account_receivable.id,
                'address': self.party.addresses[0].id,
                'gateway': gateway.id,
                'amount': 400,
            }])

        self.assertTrue(
            self.PaymentGatewayTransaction.search([
                ('rec_name', 'ilike', '%' + transaction.uuid + '%'),
                ('rec_name', 'ilike', '%' + transaction.party.name + '%')
            ])
        )

    def _get_account_by_kind(self, kind, company=None, silent=True):
        """Returns an account with given spec

        :param kind: receivable/payable/expense/revenue
        :param silent: dont raise error if account is not found
        """
        Account = POOL.get('account.account')
        Company = POOL.get('company.company')

        if company is None:
            company, = Company.search([], limit=1)

        accounts = Account.search([
            ('kind', '=', kind),
            ('company', '=', company)
        ], limit=1)
        if not accounts and not silent:
            raise Exception("Account not found")
        if not accounts:
            return None
        account, = accounts
        return account

    def setup_defaults(self):
        """
        Creates default data for testing
        """
        currency, = self.Currency.create([{
            'name': 'US Dollar',
            'code': 'USD',
            'symbol': '$',
        }])

        with Transaction().set_context(company=None):
            company_party, = self.Party.create([{
                'name': 'Openlabs'
            }])

        self.company, = self.Company.create([{
            'party': company_party,
            'currency': currency,
        }])

        self.User.write([self.User(USER)], {
            'company': self.company,
            'main_company': self.company,
        })

        CONTEXT.update(self.User.get_preferences(context_only=True))

        # Create Fiscal Year
        self._create_fiscal_year(company=self.company.id)
        # Create Chart of Accounts
        self._create_coa_minimal(company=self.company.id)
        # Create Cash journal
        self.cash_journal, = self.Journal.search(
            [('type', '=', 'cash')], limit=1
        )
        self.Journal.write([self.cash_journal], {
            'debit_account': self._get_account_by_kind('expense').id
        })

        # Create a party
        self.party, = self.Party.create([{
            'name': 'Test party',
            'addresses': [('create', [{
                'name': 'Test Party',
                'street': 'Test Street',
                'city': 'Test City',
            }])],
            'account_receivable': self._get_account_by_kind(
                'receivable').id,
        }])

    @with_transaction()
    def test_0010_test_manual_transaction(self):
        """
        Test manual transaction
        """
        self.setup_defaults()

        gateway, = self.PaymentGateway.create([{
            'name': 'Test Gateway',
            'journal': self.cash_journal.id,
            'provider': 'self',
            'method': 'manual',
        }])

        with Transaction().set_context({'company': self.company.id}):
            transaction, = self.PaymentGatewayTransaction.create([{
                'party': self.party.id,
                'credit_account': self.party.account_receivable.id,
                'address': self.party.addresses[0].id,
                'gateway': gateway.id,
                'amount': 400,
            }])
            self.assert_(transaction)

            # Process transaction
            self.PaymentGatewayTransaction.process([transaction])
            # Assert that transaction state is completed
            self.assertEqual(transaction.state, 'completed')

            # Assert that there are no account moves
            self.assertEqual(self.AccountMove.search([], count="True"), 0)

            # Post transaction
            self.PaymentGatewayTransaction.post([transaction])
            # Assert that the transaction is done
            self.assertEqual(transaction.state, 'posted')
            # Assert that an account move is created
            self.assertEqual(self.AccountMove.search([], count="True"), 1)
            self.assertEqual(self.party.receivable_today, -400)
            self.assertEqual(self.cash_journal.debit_account.balance, 400)

    @with_transaction()
    def test_0210_test_dummy_gateway(self):
        """
        Test dummy gateway transaction
        """
        self.setup_defaults()

        with Transaction().set_context(
                company=self.company.id, use_dummy=True):
            gateway, = self.PaymentGateway.create([{
                'name': 'Dummy Gateway',
                'journal': self.cash_journal.id,
                'provider': 'dummy',
                'method': 'credit_card',
            }])
            transaction, = self.PaymentGatewayTransaction.create([{
                'party': self.party.id,
                'credit_account': self.party.account_receivable.id,
                'address': self.party.addresses[0].id,
                'gateway': gateway.id,
                'amount': 400,
            }])
            self.assert_(transaction)

            # Process transaction
            with self.assertRaises(UserError):
                self.PaymentGatewayTransaction.process([transaction])

    @with_transaction()
    def test_0220_test_dummy_gateway(self):
        """
        Test dummy gateway transaction
        """
        self.setup_defaults()

        with Transaction().set_context(
                company=self.company.id, use_dummy=True):
            gateway, = self.PaymentGateway.create([{
                'name': 'Dummy Gateway',
                'journal': self.cash_journal.id,
                'provider': 'dummy',
                'method': 'credit_card',
            }])
            transaction, = self.PaymentGatewayTransaction.create([{
                'party': self.party.id,
                'credit_account': self.party.account_receivable.id,
                'address': self.party.addresses[0].id,
                'gateway': gateway.id,
                'amount': 400,
            }])
            self.assert_(transaction)

            # Now authorize and capture a transaction with this
            self.PaymentGatewayTransaction.authorize([transaction])
            self.assertEqual(transaction.state, 'authorized')

            # Now settle this transaction
            self.PaymentGatewayTransaction.settle([transaction])
            self.assertEqual(transaction.state, 'posted')
            # Assert that an account move is created
            self.assertEqual(self.AccountMove.search([], count="True"), 1)
            self.assertEqual(self.party.receivable_today, -400)
            self.assertEqual(self.cash_journal.debit_account.balance, 400)

    @with_transaction()
    def test_0220_test_dummy_profile_add(self):
        """
        Test dummy gateway profile addition
        """
        AddPaymentProfileWizard = POOL.get(
            'party.party.payment_profile.add', type='wizard'
        )
        self.setup_defaults()

        with Transaction().set_context(
                company=self.company.id, use_dummy=True):

            gateway, = self.PaymentGateway.create([{
                'name': 'Dummy Gateway',
                'journal': self.cash_journal.id,
                'provider': 'dummy',
                'method': 'credit_card',
            }])

            # create a profile
            profile_wiz = AddPaymentProfileWizard(
                AddPaymentProfileWizard.create()[0]
            )
            profile_wiz.card_info.party = self.party.id
            profile_wiz.card_info.address = self.party.addresses[0].id
            profile_wiz.card_info.provider = gateway.provider
            profile_wiz.card_info.gateway = gateway
            profile_wiz.card_info.owner = self.party.name
            profile_wiz.card_info.number = '4111111111111111'
            profile_wiz.card_info.expiry_month = '11'
            profile_wiz.card_info.expiry_year = '2018'
            profile_wiz.card_info.csc = '353'
            profile_wiz.transition_add()

    @with_transaction()
    def test_0220_test_dummy_gateway_authorize_fail(self):
        """
        Test dummy gateway transaction for authorization failure
        """
        self.setup_defaults()

        with Transaction().set_context(
                company=self.company.id, use_dummy=True):
            gateway, = self.PaymentGateway.create([{
                'name': 'Dummy Gateway',
                'journal': self.cash_journal.id,
                'provider': 'dummy',
                'method': 'credit_card',
            }])
            transaction, = self.PaymentGatewayTransaction.create([{
                'party': self.party.id,
                'credit_account': self.party.account_receivable.id,
                'address': self.party.addresses[0].id,
                'gateway': gateway.id,
                'amount': 400,
            }])
            self.assert_(transaction)

            with Transaction().set_context(dummy_succeed=False):
                # Now authorize and capture a transaction with this
                self.PaymentGatewayTransaction.authorize([transaction])

            self.assertEqual(transaction.state, 'failed')

    @with_transaction()
    def test_0220_test_dummy_gateway_capture(self):
        """
        Test dummy gateway transaction for authorization failure
        """
        self.setup_defaults()

        with Transaction().set_context(
                company=self.company.id, use_dummy=True):
            gateway, = self.PaymentGateway.create([{
                'name': 'Dummy Gateway',
                'journal': self.cash_journal.id,
                'provider': 'dummy',
                'method': 'credit_card',
            }])
            transaction, = self.PaymentGatewayTransaction.create([{
                'party': self.party.id,
                'credit_account': self.party.account_receivable.id,
                'address': self.party.addresses[0].id,
                'gateway': gateway.id,
                'amount': 400,
            }])
            self.assert_(transaction)

            self.PaymentGatewayTransaction.capture([transaction])

            self.assertEqual(transaction.state, 'posted')
            # Assert that an account move is created
            self.assertEqual(self.AccountMove.search([], count="True"), 1)
            self.assertEqual(self.party.receivable_today, -400)
            self.assertEqual(self.cash_journal.debit_account.balance, 400)

    @with_transaction()
    def test_0220_test_dummy_gateway_capture_fail(self):
        """
        Test dummy gateway transaction for authorization failure
        """
        self.setup_defaults()

        with Transaction().set_context(
                company=self.company.id, use_dummy=True):
            gateway, = self.PaymentGateway.create([{
                'name': 'Dummy Gateway',
                'journal': self.cash_journal.id,
                'provider': 'dummy',
                'method': 'credit_card',
            }])
            transaction, = self.PaymentGatewayTransaction.create([{
                'party': self.party.id,
                'credit_account': self.party.account_receivable.id,
                'address': self.party.addresses[0].id,
                'gateway': gateway.id,
                'amount': 400,
            }])
            self.assert_(transaction)

            with Transaction().set_context(dummy_succeed=False):
                self.PaymentGatewayTransaction.capture([transaction])

            self.assertEqual(transaction.state, 'failed')

    @with_transaction()
    def test_0230_manual_gateway_auth_settle(self):
        """
        Test authorize and capture with the manual payment gateway
        """
        self.setup_defaults()

        gateway, = self.PaymentGateway.create([{
            'name': 'Test Gateway',
            'journal': self.cash_journal.id,
            'provider': 'self',
            'method': 'manual',
        }])

        with Transaction().set_context({'company': self.company.id}):
            transaction, = self.PaymentGatewayTransaction.create([{
                'party': self.party.id,
                'credit_account': self.party.account_receivable.id,
                'address': self.party.addresses[0].id,
                'gateway': gateway.id,
                'amount': 400,
            }])
            self.assert_(transaction)

            # Process transaction
            self.PaymentGatewayTransaction.authorize([transaction])
            self.assertEqual(transaction.state, 'authorized')
            # Assert that an account move is **not** created
            self.assertEqual(self.AccountMove.search([], count="True"), 0)
            self.assertEqual(self.party.receivable_today, 0)
            self.assertEqual(self.cash_journal.debit_account.balance, 0)

            # Capture transaction
            self.PaymentGatewayTransaction.settle([transaction])

            transaction = self.PaymentGatewayTransaction(transaction.id)
            # Assert that the transaction is done
            self.assertEqual(transaction.state, 'posted')

            # Assert that an account move is created
            self.assertEqual(self.AccountMove.search([], count="True"), 1)
            self.assertEqual(self.party.receivable_today, -400)
            self.assertEqual(self.cash_journal.debit_account.balance, 400)

    @with_transaction()
    def test_0240_manual_gateway_capture(self):
        """
        Test authorize and capture with the manual payment gateway
        """
        self.setup_defaults()

        gateway, = self.PaymentGateway.create([{
            'name': 'Test Gateway',
            'journal': self.cash_journal.id,
            'provider': 'self',
            'method': 'manual',
        }])

        with Transaction().set_context({'company': self.company.id}):
            transaction, = self.PaymentGatewayTransaction.create([{
                'party': self.party.id,
                'credit_account': self.party.account_receivable.id,
                'address': self.party.addresses[0].id,
                'gateway': gateway.id,
                'amount': 400,
            }])
            self.assert_(transaction)

            # Process transaction
            self.PaymentGatewayTransaction.capture([transaction])
            self.assertEqual(transaction.state, 'posted')

            # Assert that an account move is created
            self.assertEqual(self.AccountMove.search([], count="True"), 1)
            self.assertEqual(self.party.receivable_today, -400)
            self.assertEqual(self.cash_journal.debit_account.balance, 400)

    @with_transaction()
    def test_0250_gateway_configuration(self):
        """
        Test the configuration of payment gateway
        """
        self.setup_defaults()

        gateway, = self.PaymentGateway.create([{
            'name': 'Test Gateway',
            'journal': self.cash_journal.id,
            'provider': 'self',
            'method': 'manual',
        }])
        self.PaymentGateway.test_gateway_configuration([gateway])
        self.assertTrue(gateway.configured)

        # Mark party required on journals's debit account and check if
        # configuration is wrong
        account = self.cash_journal.debit_account
        account.party_required = True
        account.save()

        self.PaymentGateway.test_gateway_configuration([gateway])
        self.assertFalse(gateway.configured)

    @with_transaction()
    def test_0260_test_dummy_delete_move(self):
        """
        Test if the account move is deleted is transaction fails to post
        using safe post
        """
        self.setup_defaults()

        with Transaction().set_context(
                company=self.company.id, use_dummy=True):
            gateway, = self.PaymentGateway.create([{
                'name': 'Dummy Gateway',
                'journal': self.cash_journal.id,
                'provider': 'dummy',
                'method': 'credit_card',
            }])
            # Mark party required so that move does not post
            account = self.cash_journal.debit_account
            account.party_required = True
            account.save()

            transaction, = self.PaymentGatewayTransaction.create([{
                'party': self.party.id,
                'credit_account': self.party.account_receivable.id,
                'address': self.party.addresses[0].id,
                'gateway': gateway.id,
                'amount': 400,
            }])
            self.assert_(transaction)

            self.PaymentGatewayTransaction.capture([transaction])

            # Test if transaction failed to post
            self.assertEqual(transaction.state, 'completed')
            # Check that the account move was deleted
            self.assertEqual(len(transaction.logs), 1)
            self.assertTrue(
                "Deleted account move" in transaction.logs[0].log)


def suite():
    "Define suite"
    test_suite = trytond.tests.test_tryton.suite()
    test_suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(TestTransaction)
    )
    return test_suite


if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
