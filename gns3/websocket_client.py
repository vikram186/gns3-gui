# -*- coding: utf-8 -*-
#
# Copyright (C) 2014 GNS3 Technologies Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
Non-blocking Websocket client with JSON-RPC support to connect to GNS3 servers.
Based on the ws4py websocket client.
"""

import json
import jsonrpc
from ws4py.client import WebSocketBaseClient
from .qt import QtCore

import logging
log = logging.getLogger(__name__)


class WebSocketClient(WebSocketBaseClient):
    """
    Websocket client.

    :param url: websocket URL to connect to the server
    """

    def __init__(self, url, protocols=None, extensions=None, heartbeat_freq=None,
                 ssl_options=None, headers=None):

        WebSocketBaseClient.__init__(self, url, protocols, extensions, heartbeat_freq,
                                     ssl_options, headers=headers)

        self.callbacks = {}
        self._connected = False

    def opened(self):
        """
        Called when the connection with the server is successful.
        """

        log.info("connected to {}:{}".format(self.host, self.port))
        self._connected = True

    @property
    def connected(self):
        """
        Returns if the client is connected.

        :returns: True or False
        """

        return self._connected

    def handshake_ok(self):
        """
        Called when the connection has been established with the server and
        monitors the connection using the QSocketNotifier.
        """

        fd = self.connection.fileno()
        # we are interested in all data received.
        self.fd_notifier = QtCore.QSocketNotifier(fd, QtCore.QSocketNotifier.Read)
        self.fd_notifier.activated.connect(self.data_received)
        self.opened()

    def closed(self, code, reason):
        """
        Called when the connection has been closed.

        :param code: code (integer)
        :param reason: reason (string)
        """

        log.info("Connection closed down: {} (code {})".format(reason, code))
        self._connected = False

    def received_message(self, message):
        """
        Called when a new message has been received from the server.

        :param message: message object
        """

        # TODO: WSAEWOULDBLOCK on Windows
        if not message.is_text:
            log.warning("received data is not text")
            return

        try:
            reply = json.loads(message.data.decode("utf-8"))
        except:
            log.warning("received data is not valid JSON")
            return

        if "result" in reply:
        # This is a JSON-RPC result
            request_id = reply.get("id")
            result = reply.get("result")
            if request_id in self.callbacks:
                self.callbacks[request_id](result)
                del self.callbacks[request_id]
            else:
                log.warning("unknown JSON-RPC request ID received {}".format(request_id))

        elif "error" in reply:
            # This is a JSON-RPC error
            error_message = reply["error"].get("message")
            error_code = reply["error"].get("code")
            request_id = reply.get("id")
            if request_id in self.callbacks:
                self.callbacks[request_id](reply["error"], True)
                del self.callbacks[request_id]
            else:
                log.warning("received JSON-RPC error {}: {} for request ID {}".format(error_code,
                                                                                      error_message,
                                                                                      request_id))
        elif "method" in reply:
            # This is a JSON-RPC notification
            method = reply.get("method")
            params = reply.get("params")
            #TODO: handle notifications from servers
            print("This is a notification! {} {}".format(method, params))

    def send_message(self, destination, params, callback):
        """
        Sends a message to the server.

        :param destination: server destination method
        :param params: params to send (dictionary)
        :param callback: callback method to call when the server replies.
        """

        request = jsonrpc.JSONRPCRequest(destination, params)
        self.callbacks[request.id] = callback
        self.send(str(request))

    def send_notification(self, destination, params=None):
        """
        Sends a notification to the server. No reply is expected from the server.

        :param destination: server destination method
        :param params: params to send (dictionary)
        """

        request = jsonrpc.JSONRPCNotification(destination, params)
        self.send(str(request))

    def close_connection(self):
        """
        Closes the connection to the server and remove the monitoring by
        the QSocketNotifier.
        """

        WebSocketBaseClient.close_connection(self)
        self.fd_notifier.setEnabled(False)

    def data_received(self, fd):
        """
        Callback called when data is received from the server.
        """

        # read the data, if successful received_message() is called by once()
        if self.once() == False:
            log.warning("lost connection with server {}:{}".format(self.host, self.port))
            self.close_connection()