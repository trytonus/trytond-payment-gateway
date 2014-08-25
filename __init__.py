# -*- coding: utf-8 -*-
'''

    Payment Gateway

    :copyright: (c) 2013-2014 by Openlabs Technologies & Consulting (P) Ltd.
    :license: BSD, see LICENSE for more details

'''
from trytond.pool import Pool
from .transaction import PaymentTransaction, TransactionLog, PaymentGateway, \
    PaymentProfile, AddPaymentProfileView, \
    AddPaymentProfile, Party, TransactionUseCardView, TransactionUseCard
from .dummy import PaymentGatewayDummy, AddPaymentProfileViewDummy, \
    AddPaymentProfileDummy, DummyTransaction
from .manual import PaymentGatewaySelf, ManualSelfTransaction


def register():
    Pool.register(
        Party,
        PaymentGateway,
        PaymentProfile,
        PaymentTransaction,
        TransactionLog,
        AddPaymentProfileView,
        TransactionUseCardView,
        # Dummy provider related classes
        PaymentGatewayDummy,
        AddPaymentProfileViewDummy,
        DummyTransaction,
        # Manualself run payment gateway
        PaymentGatewaySelf,
        ManualSelfTransaction,
        module='payment_gateway', type_='model'
    )
    Pool.register(
        AddPaymentProfile,
        AddPaymentProfileDummy,
        TransactionUseCard,
        module='payment_gateway', type_='wizard'
    )
