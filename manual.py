# -*- coding: utf-8 -*-
'''

    Manual payment gateway

    Often payment modes are offline like cash, external credit card terminals
    etc. This gateway implements that

    :copyright: (c) 2013-2014 by Openlabs Technologies & Consulting (P) Ltd.
    :license: BSD, see LICENSE for more details

'''
from trytond.pool import PoolMeta

__metaclass__ = PoolMeta


class PaymentGatewaySelf:
    "COD, Cheque and Bank Transfer Implementation"
    __name__ = 'payment_gateway.gateway'

    @classmethod
    def get_providers(cls, values=None):
        """
        Downstream modules can add to the list
        """
        rv = super(PaymentGatewaySelf, cls).get_providers()
        self_record = ('self', 'Self')
        if self_record not in rv:
            rv.append(self_record)
        return rv

    def get_methods(self):
        if self.provider == 'self':
            return [
                ('manual', 'Manual/Offline'),
            ]
        return super(PaymentGatewaySelf, self).get_methods()


class ManualSelfTransaction:
    """
    Implement the authorize and capture methods
    """
    __name__ = 'payment_gateway.transaction'

    def authorize_self(self, card_info=None):
        """
        Authorize a manual payment
        """
        self.state = 'authorized'
        self.save()

    def settle_self(self):
        """
        Capture a manual payment.
        All that needs to be done is post the transaction.
        """
        self.state = 'completed'
        self.save()
        self.safe_post()

    def capture_self(self):
        """
        Capture a manual payment.
        All that needs to be done is post the transaction.
        """
        self.state = 'completed'
        self.save()
        self.safe_post()

    def cancel_dummy(self):
        """
        Cancel a dummy transaction
        """
        if self.state != 'authorized':
            self.raise_user_error('cancel_only_authorized')
        else:
            self.state = 'cancel'
            self.save()
