#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2024 Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/


import logging
import threading
import urllib.parse

import requests

from .base import TelemetryBase


logger = logging.getLogger(__name__)


class TelemetryClient(TelemetryBase):
    """Represents a telemetry python client providing functions to record an event.

    Methods
    -------
    record_event(category: str = None, action: str = None, path: str = None, **kwargs) -> None
        Send a head request to generate an event record.
    record_event_async(category: str = None, action: str = None, path: str = None,  **kwargs)
        Starts thread to send a head request to generate an event record.

    Examples
    --------
    >>> import os
    >>> from ads.telemetry.client import TelemetryClient
    >>> AQUA_BUCKET = os.environ.get("AQUA_BUCKET", "service-managed-models")
    >>> AQUA_BUCKET_NS = os.environ.get("AQUA_BUCKET_NS", "ociodscdev")
    >>> telemetry = TelemetryClient(bucket=AQUA_BUCKET, namespace=AQUA_BUCKET_NS)
    >>> category = "aqua/service/model"
    >>> action = "list"
    >>> telemetry.record_event_async(category=f"telemetry/{category}", action=action)
    """

    @staticmethod
    def _encode_user_agent(**kwargs):
        message = urllib.parse.urlencode(kwargs)
        return message

    def record_event(self, category: str = None, action: str = None, path: str = None, **kwargs) -> None:
        """Send a head request to generate an event record.

        Parameters
        ----------
        category (str)
            Category of the event, which is also the path to the directory containing the object representing the event.
        action (str)
            Filename of the object representing the event.
        path (str)
            The path of the object representing the event, e.g. "telemetry/conda/delete".

        Returns
        -------
        Response
        """
        if category and action:
            path = f"{category}/{action}"
        if not path:
            raise ValueError("Please specify either the combination of category and action, or path")
        endpoint = f"{self.service_endpoint}/n/{self.namespace}/b/{self.bucket}/o/{path}"
        headers = {"User-Agent": self._encode_user_agent(**kwargs)}
        logger.debug(f"Sending telemetry to endpoint: {endpoint}")
        response = requests.head(endpoint, auth=self._auth, headers=headers)
        logger.debug(f"Telemetry status code: {response.status_code}")
        return response

    def record_event_async(self, category: str = None, action: str = None, path: str = None, **kwargs):
        """Send a head request to generate an event record.

        Parameters
        ----------
        category (str)
            Category of the event, which is also the path to the directory containing the object representing the event.
        action (str)
            Filename of the object representing the event.
        path (str)
            The path of the object representing the event, e.g. "telemetry/conda/delete".

        Returns
        -------
        Thread
            A started thread to send a head request to generate an event record.
        """
        thread = threading.Thread(
            target=self.record_event,
            args=(category, action, path),
            kwargs=kwargs
        )
        thread.daemon = True
        thread.start()
        return thread
