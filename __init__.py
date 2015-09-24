# -*- coding: utf-8 -*-
from trytond.pool import Pool
from .transaction import PaymentTransaction, TransactionLog, PaymentGateway, \
    PaymentProfile, AddPaymentProfileView, \
    AddPaymentProfile, Party, TransactionUseCardView, TransactionUseCard, \
    PaymentGatewayResUser, User, AccountMove, CreateRefund
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
        PaymentGatewayResUser,
        User,
        AccountMove,
        module='payment_gateway', type_='model'
    )
    Pool.register(
        AddPaymentProfile,
        AddPaymentProfileDummy,
        TransactionUseCard,
        CreateRefund,
        module='payment_gateway', type_='wizard'
    )
