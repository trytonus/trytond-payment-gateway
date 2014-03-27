# -*- coding: utf-8 -*-
'''

    Payment Gateway

    :copyright: (c) 2013-2014 by Openlabs Technologies & Consulting (P) Ltd.
    :license: BSD, see LICENSE for more details

'''
from trytond.pool import Pool
from .transaction import PaymentTransaction, TransactionLog, PaymentGateway, \
    PaymentGatewaySelf, PaymentProfile, AddPaymentProfileView, \
    AddPaymentProfile, Party, TransactionUseCardView, TransactionUseCard


def register():
    Pool.register(
        Party,
        PaymentGateway,
        PaymentGatewaySelf,
        PaymentProfile,
        PaymentTransaction,
        TransactionLog,
        AddPaymentProfileView,
        TransactionUseCardView,
        module='payment_gateway', type_='model'
    )
    Pool.register(
        AddPaymentProfile,
        TransactionUseCard,
        module='payment_gateway', type_='wizard'
    )
