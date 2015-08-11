Writing a payment gateway module
================================

This is a developer guide for programmers wanting to write a
payment_gateway for a payment provider. This guide assumes a beginner
level of expertise in writing modules for Tryton.

The examples in the case use Authorize.net as an example. The completely
built module can be seen on github (`payment-gateway-authorize-net 
<https://github.com/fulfilio/trytond-payment-gateway-authorize-net>`_).

Step 0: Identify a qualified name for the provider
--------------------------------------------------

To keep the code simple, the payment-gateway module appends the name of
the provider to method names and expects them to exist in the models. This
requires that you use a consistent provider name which can also be a valid
identifier in python.

In this example the provider name chosen is `authorize_net` for
Authorize.net. Though it is not a requirement, the identifier is all in
small case as python identifiers are case sensitive and method names by
coding convention use small case.

Step 1: Setup the payment gateway fields for configuration
----------------------------------------------------------

Every payment gateway has a different way of authentication and
requirements. Hence, the only common component the base module offers you
is a :py:attr:`~transaction.PaymentGateway.test` boolean field if the
gateway is working in a test mode or production.


Add provider name to providers selection list
``````````````````````````````````````````````

As you can see in the code above, the fields' properties are based on the
value of the provider field which is a 
:py:class:`trytond.model.fields.Selection` in which the options are returned by
the :py:meth:`~transaction.PaymentGateway.get_providers` method. So the
code also needs to inject `authorize_net` as an option.::

    @classmethod
    def get_providers(cls, values=None):
        """
        Add authorize_net as a provider option.
        """
        rv = super(PaymentGatewayAuthorize, cls).get_providers()
        authorize_record = ('authorize_net', 'Authorize.net')
        if authorize_record not in rv:
            rv.append(authorize_record)
        return rv

The model also includes a method selection field in which the values are
added dynamically based on the chosen provider. This is achieved using the
:py:attr:`~trytond.model.fields.Reference.selection_change_with`
functionality of selection fields.::

    def get_methods(self):
        if self.provider == 'authorize_net':
            return [
                ('credit_card', 'Credit Card - Authorize.net'),
            ]
        return super(PaymentGatewayAuthorize, self).get_methods()


The currently recognised types and the special features attached to them
are:

====================== =================================================
Method name             Description
====================== =================================================
`credit_card`           When credit card is the method chosen, the 
                        payment transaction form shows the `Enter Credit
                        Card` button. Other methods are considered as
                        off-line payment methods, with no special
                        functionality attached to it.
====================== =================================================

.. note::

   Future versions of the module may support additional methods like
   `Electronic Bill payments (EBP)` and `Automated Clearing House (ACH)`
   which works like electronic versions of cheques.


Add gateway specific fields to the model
`````````````````````````````````````````

Authorize.net requires a `login` and `transaction_key` to interact with
it's web service API. So the two fields can be created into the
payment_gateway.gateway module::

    class PaymentGatewayAuthorize:
        __name__ = 'payment_gateway.gateway'

        authorize_net_login = fields.Char(
            'API Login', states={
                'required': Eval('provider') == 'authorize_net',
                'invisible': Eval('provider') != 'authorize_net',
            }, depends=['provider']
        )
        authorize_net_transaction_key = fields.Char(
            'Transaction Key', states={
                'required': Eval('provider') == 'authorize_net',
                'invisible': Eval('provider') != 'authorize_net',
            }, depends=['provider']
        )

.. tip::

   The states make the field appear only when the chosen provider is
   Authorize.net. The fields are also required only when Authorize.net is
   the gateway.


Add the fields to the view
``````````````````````````

The fields above will not be available on the view of the gateway unless
explicitly added using XML. The base module provides an empty notebook
into which pages can be added which are displayed based on the value of
the :py:attr:`~transaction.PaymentGateway.provider` selection field.

.. code-block:: xml

    
    <!-- XML record for the view which inherits gateway form view -->
    <record model="ir.ui.view" id="gateway_view_form">
        <field name="model">payment_gateway.gateway</field>
        <field name="inherit" ref="payment_gateway.gateway_view_form"/>
        <field name="name">gateway_form</field>
    </record>

And the view code could be something like:

.. code-block:: xml

    <?xml version="1.0"?>
    <data>
        <xpath expr="/form/notebook" position="inside">
            <page string="Authorize.net Settings" id="authorize_net"
                    states="{'invisible': Eval('provider') != 'authorize_net'}">
                <label name="authorize_net_login"/>
                <field name="authorize_net_login"/>
                <label name="authorize_net_transaction_key"/>
                <field name="authorize_net_transaction_key"/>
            </page>
        </xpath>
    </data>

.. note::

   The empty notebook in the original view 
   (`payment_gateway.gateway_view_form`) in the xpath `/form/notebook`
   offers a simple way to add payment gateway specific configuration
   fields on a separate notebook page which is visible only when the
   gateway which defines them is chosen.

Step 2: Add Methods for transactions
------------------------------------

Payment gateway transaction usually involve the following operations.
The method names used for the same are also highlighted in the table.

================ =========================== ============ =======================
Operation        Description                 Prefix          Example
================ =========================== ============ =======================
`Authorization`_ Authorization hold (also    `authorize_` authorize_authorize_net
                 card authorization, 
                 preauthorization, or 
                 preauth) is the practice
                 within the banking 
                 industry of authorizing
                 electronic transactions
                 done with a debit card
                 or credit card and 
                 holding this balance 
                 as unavailable either
                 until the merchant 
                 clears the transaction
                 (also called 
                 settlement), 
                 or the hold 
                 "falls off."                              
`Settle`_        Credit card settlement      `settle_`    settle_authorize_net
                 is the process by which
                 authorized transactions
                 are submitted to card 
                 issuers for payment.
`Capture`_       Capture is the process      `capture_`   capture_authorize_net
                 of performing an
                 authorization and
                 settlement at once 
                 without having separate
                 steps.
Retry            When a transaction fails    `retry_`     retry_authorize_net
                 some gateways offer the
                 option to retry the
                 transaction which failed.
Update           Update the transaction      `update_`    update_authorize_net
                 status.
Cancel           Cancel an authorization     `cancel_`    cancel_authorize_net
================ =========================== ============ =======================

Not all of the above methods need to be implemented for a gateway to be
useful. The `capture` method is a minimum requirement for a functional
gateway.

.. note::

   This example uses a third party python module called `authorize_sause
   <http://authorize-sauce.readthedocs.org/en/latest/>`_ to interact with
   authorize.net.


Authorization
`````````````

.. py:method:: authorize_authorize_net([, card_info])
    
    Authorize the current transaction with the card (if provided) or the
    :py:attr:`~transaction.PaymentTransaction.payment_profile`.

    :param card_info: An instance of :py:class:`~transaction.CreditCardView`
    :raises UserError: If card and profile are missing.


This instance method receives the transaction to be authorized as its
instance (`self`) and optionally `card_info` if a card was entered for the
transaction to be processed. The `card_info` is available only when the
transaction processed using a card. Alternatively, a previously stored
:ref:`payment profile <payment-profile>` could have been specified in the
:py:attr:`~transaction.PaymentTransaction.payment_profile` field::

    def authorize_authorize_net(self, card_info=None):
        """
        Authorize using authorize.net for the specific transaction.

        :param credit_card: An instance of CreditCardView
        :raises UserError: If card and profile are missing.        
        """
        TransactionLog = Pool().get('payment_gateway.transaction.log')

        client = self.gateway.get_authorize_client()

        # A hack to inject the currency paramater into base_params of the
        # authorize sause transaction API since the implementation iself
        # does not offer a better way of handling currency
        client._transaction.base_params['x_currency_code'] = self.currency.code

        if card_info:
            # Card information is specified, so create a Credit Card
            cc = CreditCard(
                card_info.number,
                card_info.expiry_year,
                card_info.expiry_month,
                card_info.csc,
                card_info.owner,
            )
            credit_card = client.card(cc)
        elif self.payment_profile:
            # A stored payment profile is used to process the transaction.
            # Use the saved card instead
            credit_card = client.saved_card(
                self.payment_profile.provider_reference
            )
        else:
            self.raise_user_error('no_card_or_profile')

        try:
            # try to authorize the card for the amount in the transaction
            result = credit_card.auth(self.amount)
        except AuthorizeResponseError, exc:
            # This error is raised when Authorize.net returns an error
            # response
            self.state = 'failed'
            self.save()

            # The full response of the error is part of the exception
            # raised, store that in the logs for easy debugging.
            TransactionLog.serialize_and_create(self, exc.full_response)
        else:
            # the authorization was succesful, so set the state and save
            self.state = 'authorized'
            self.provider_reference = str(result.uid)
            self.save()

            # Save the full response either way into the logs
            TransactionLog.serialize_and_create(self, result.full_response)

Settle
```````

.. py:method:: settle_authorize_net()
    
    Settle the current transaction for the full amount.



This instance method receives the transaction to be authorized as its
instance (`self`). On being called it attempts to settle the complete
amount of the transaction with the service provider. Future versions may
support the ability to have partial settlements.::

    def settle_authorize_net(self):
        """
        Settles this transaction if it is a previous authorization.
        """
        TransactionLog = Pool().get('payment_gateway.transaction.log')

        client = self.gateway.get_authorize_client()

        # A hack to inject the currency paramater into base_params of the
        # authorize sause transaction API since the implementation iself
        # does not offer a better way of handling currency        
        client._transaction.base_params['x_currency_code'] = self.currency.code

        auth_net_transaction = client.transaction(self.provider_reference)
        try:
            # Try to settle the transaction
            result = auth_net_transaction.settle()
        except AuthorizeResponseError, exc:
            # This error is raised whn Authorize.net returns an error
            # response        
            self.state = 'failed'
            self.save()
            TransactionLog.serialize_and_create(self, exc.full_response)
        else:
            # Mark the transaction as completed.
            self.state = 'completed'
            self.provider_reference = str(result.uid)
            self.save()
            TransactionLog.serialize_and_create(self, result.full_response)

            # Try to post the transaction
            self.safe_post()

.. tip::

   The :py:meth:`~transaction.PaymentTransaction.safe_post` method is a
   helper which tries to post the transaction, but on failure, it ignores
   the attempt without an error. This is important as an error at this
   stage would mean the transaction state being changed on the service
   provider while tryton may not have the right status because the
   error caused a rollback.

Capture
````````

.. py:method:: capture_authorize_net([, card_info])
    
    Capture and complete the current transaction with the card 
    (if provided) or the 
    :py:attr:`~transaction.PaymentTransaction.payment_profile`.

    :param card_info: An instance of :py:class:`~transaction.CreditCardView`
    :raises UserError: If card and profile are missing.


This instance method receives the transaction to be authorized as its
instance (`self`) and optionally `card_info` if a card was entered for the
transaction to be processed. The `card_info` is available only when the
transaction processed using a card. Alternatively, a previously stored
:ref:`payment profile <payment-profile>` could have been specified in the
:py:attr:`~transaction.PaymentTransaction.payment_profile` field::

    def capture_authorize_net(self, card_info=None):
        """
        Capture using authorize.net for the specific transaction.

        :param card_info: An instance of CreditCardView
        """
        TransactionLog = Pool().get('payment_gateway.transaction.log')

        client = self.gateway.get_authorize_client()

        # A hack to inject the currency paramater into base_params of the
        # authorize sause transaction API since the implementation iself
        # does not offer a better way of handling currency           
        client._transaction.base_params['x_currency_code'] = self.currency.code

        if card_info:
            cc = CreditCard(
                card_info.number,
                card_info.expiry_year,
                card_info.expiry_month,
                card_info.csc,
                card_info.owner,
            )
            credit_card = client.card(cc)
        elif self.payment_profile:
            # A stored payment profile is used to process the transaction.
            # Use the saved card instead        
            credit_card = client.saved_card(
                self.payment_profile.provider_reference
            )
        else:
            self.raise_user_error('no_card_or_profile')

        try:
            result = credit_card.capture(self.amount)
        except AuthorizeResponseError, exc:
            self.state = 'failed'
            self.save()
            TransactionLog.serialize_and_create(self, exc.full_response)
        else:
            self.state = 'completed'
            self.provider_reference = str(result.uid)
            self.save()
            TransactionLog.serialize_and_create(self, result.full_response)
            self.safe_post()

Cancel
``````

.. py:method:: cancel_authorize_net()
    
    Cancel the current transaction authorization.

With authorize.net cancellation `Voids` a previous authorization that has not 
yet been settled::

    def cancel_authorize_net(self):
        """
        Cancel this authorization or request
        """
        TransactionLog = Pool().get('payment_gateway.transaction.log')

        if self.state != 'authorized':
            self.raise_user_error('cancel_only_authorized')

        client = self.gateway.get_authorize_client()
        client._transaction.base_params['x_currency_code'] = self.currency.code

        auth_net_transaction = client.transaction(self.provider_reference)

        # Try to void the transaction
        result = auth_net_transaction.void()

        # Mark the state as cancelled
        self.state = 'cancel'
        self.save()

        TransactionLog.serialize_and_create(self, result.full_response)


Step 3: Add support for payment profiles (Optional)
---------------------------------------------------

If the gateway you are writing supports storing confidential credit card
information for later use, the provider could be added to the supported
providers for maintaining payment profiles of parties.

The addition of a payment profile is expected to add the card to the
payment provider's vault and return a unique reference to it which is
stored in :py:attr:`~PaymentProfile.provider_reference` field.

Add provider to selection field
````````````````````````````````

Extend the `party.payment_profile.add_view` model to add the provider
identifier as an option in the providers selection field::

    class AddPaymentProfileView:
        __name__ = 'party.payment_profile.add_view'

        @classmethod
        def get_providers(cls):
            """
            Return the list of providers who support credit card profiles.
            """
            res = super(AddPaymentProfileView, cls).get_providers()
            res.append(('authorize_net', 'Authorize.net'))
            return res

Implement transition_add method
```````````````````````````````

The :py:class:`AddPaymentProfile` wizard offers a form to the user to fill
up confidential information which is then sent to the server. 

The API requires that a `transition_add_<provider_identifier>` method be
available which should create the card on the payment provider's server
and save the reference to the :py:attr:`~PaymentProfile.provider_reference`.

A convenience method :py:meth:`PaymentProfile.create_profile` creates a
new profile and returns the active record of the created profile, when
called with the payment provider's reference as an argument::

    class AddPaymentProfile:
        """
        Add a payment profile
        """
        __name__ = 'party.party.payment_profile.add'

        def transition_add_authorize_net(self):
            """
            Handle the case if the profile should be added for authorize.net
            """
            card_info = self.card_info

            client = card_info.gateway.get_authorize_client()
            cc = CreditCard(
                card_info.number,
                card_info.expiry_year,
                card_info.expiry_month,
                card_info.csc,
                card_info.owner,
            )
            address = Address(
                card_info.address.street,
                card_info.address.city,
                card_info.address.zip,
                card_info.address.country.code,
            )
            saved_card = AuthorizeCreditCard(
                client,
                credit_card=cc,
                address=address,
                email=card_info.party.email
            )
            saved_card = saved_card.save()
            self.create_profile(saved_card.uid)

            return 'end'


.. _Authorize: http://en.wikipedia.org/wiki/Authorization_hold
.. _Settle: https://www.chasepaymentech.com/the_basics.html
.. _Capture: https://www.chasepaymentech.com/the_basics.html
