#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2024 Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/

"""
aqua.exception
~~~~~~~~~~~~~~

This module contains the set of Aqua exceptions.
"""


class AquaError(Exception):
    """AquaError

    The base exception from which all exceptions raised by Aqua
    will inherit.
    """

    def __init__(
        self,
        reason: str,
        status: int,
        service_payload: dict = None,
    ):
        """Initializes an AquaError.

        Parameters
        ----------
        reason: str
            User friendly error message.
        status: int
            Http status code that are going to raise.
        service_payload: dict
            Payload to contain more details related to the error.
        """
        self.service_payload = service_payload or {}
        self.status = status
        self.reason = reason


class AquaValueError(AquaError, ValueError):
    """Exception raised for unexpected values."""

    def __init__(self, reason, status=403, service_payload=None):
        super().__init__(reason, status, service_payload)


class AquaFileNotFoundError(AquaError, FileNotFoundError):
    """Exception raised for missing target file."""

    def __init__(self, reason, status=404, service_payload=None):
        super().__init__(reason, status, service_payload)


class AquaRuntimeError(AquaError, RuntimeError):
    """Exception raised for generic errors at runtime."""

    def __init__(self, reason, status=400, service_payload=None):
        super().__init__(reason, status, service_payload)


class AquaMissingKeyError(AquaError):
    """Exception raised when missing metadata in resource."""

    def __init__(self, reason, status=400, service_payload=None):
        super().__init__(reason, status, service_payload)


class AquaFileExistsError(AquaError, FileExistsError):
    """Exception raised when file already exists in resource."""

    def __init__(self, reason, status=400, service_payload=None):
        super().__init__(reason, status, service_payload)
