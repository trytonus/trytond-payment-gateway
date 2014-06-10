Payment Gateway
===============

.. image:: https://travis-ci.org/openlabs/payment-gateway.png?branch=develop
  :target: https://travis-ci.org/openlabs/payment-gateway

.. image:: https://coveralls.io/repos/openlabs/payment-gateway/badge.png?branch=develop
  :target: https://coveralls.io/r/openlabs/payment-gateway

A tryton base module to accept and process payments within Tryton using
credit cards.

The base module itself does not process cards, but extension modules could
be written for each payment gateway. The currently available modules are:

================== ============================ ========================================================================
Provider            Features                    
================== ============================ ========================================================================
`Authorize.net`_    * Customer Profiles         * `Github <https://github.com/openlabs/payment-gateway-authorize-net>`_
                    * Accept Cards              * Package: openlabs_payment_gateway_authorize_net
                    * Authorize and Settle
                    * Capture
================== ============================ ========================================================================

If you have written a gateway which you would like to list here, please
send a pull request with the information.


.. _Authorize.net: http://www.authorize.net/
.. _Beanstream: http://www.beanstream.com/home/
