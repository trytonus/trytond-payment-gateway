API Reference
=============

.. toctree::
   :maxdepth: 3

.. automodule:: transaction

`payment_gateway.gateway`
-------------------------

.. autoclass:: PaymentGateway

Fields
``````
.. autoattribute:: PaymentGateway.name
.. autoattribute:: PaymentGateway.journal
.. autoattribute:: PaymentGateway.provider
.. autoattribute:: PaymentGateway.method
.. autoattribute:: PaymentGateway.test

Methods
```````

.. automethod:: PaymentGateway.get_providers

`payment_gateway.transaction`
-----------------------------

.. autoclass:: PaymentTransaction

Fields
``````

.. autoattribute:: PaymentTransaction.uuid
.. autoattribute:: PaymentTransaction.provider_reference
.. autoattribute:: PaymentTransaction.date
.. autoattribute:: PaymentTransaction.company
.. autoattribute:: PaymentTransaction.party
.. autoattribute:: PaymentTransaction.payment_profile
.. autoattribute:: PaymentTransaction.address
.. autoattribute:: PaymentTransaction.amount
.. autoattribute:: PaymentTransaction.currency
.. autoattribute:: PaymentTransaction.gateway
.. autoattribute:: PaymentTransaction.provider
.. autoattribute:: PaymentTransaction.method
.. autoattribute:: PaymentTransaction.move
.. autoattribute:: PaymentTransaction.logs
.. autoattribute:: PaymentTransaction.state


Methods
```````

.. automethod:: PaymentTransaction.safe_post

`payment_gateway.transaction.log`
---------------------------------

.. autoclass:: TransactionLog

Methods
```````

.. automethod:: TransactionLog.serialize_and_create


`party.payment_profile`
-----------------------

.. autoclass:: PaymentProfile

Fields
``````

.. autoattribute:: PaymentProfile.party
.. autoattribute:: PaymentProfile.address
.. autoattribute:: PaymentProfile.gateway
.. autoattribute:: PaymentProfile.provider_reference
.. autoattribute:: PaymentProfile.last_4_digits
.. autoattribute:: PaymentProfile.expiry_month
.. autoattribute:: PaymentProfile.expiry_year

Wizard: `party.party.payment_profile.add`
-----------------------------------------

.. autoclass:: AddPaymentProfile

Methods
```````

.. automethod:: AddPaymentProfile.create_profile
