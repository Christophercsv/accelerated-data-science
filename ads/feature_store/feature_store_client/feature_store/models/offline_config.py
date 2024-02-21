# coding: utf-8
# Copyright (c) 2016, 2024, Oracle and/or its affiliates.  All rights reserved.
# This software is dual-licensed to you under the Universal Permissive License (UPL) 1.0 as shown at https://oss.oracle.com/licenses/upl or Apache License 2.0 as shown at http://www.apache.org/licenses/LICENSE-2.0. You may choose either license.


from oci.util import formatted_flat_dict, NONE_SENTINEL, value_allowed_none_or_none_sentinel  # noqa: F401
from oci.decorators import init_model_state_from_kwargs


@init_model_state_from_kwargs
class OfflineConfig(object):
    """
    Offline configuration related information of FeatureStore.
    """

    def __init__(self, **kwargs):
        """
        Initializes a new OfflineConfig object with values from keyword arguments.
        The following keyword arguments are supported (corresponding to the getters/setters of this class):

        :param metastore_id:
            The value to assign to the metastore_id property of this OfflineConfig.
        :type metastore_id: str

        """
        self.swagger_types = {
            'metastore_id': 'str'
        }

        self.attribute_map = {
            'metastore_id': 'metastoreId'
        }

        self._metastore_id = None

    @property
    def metastore_id(self):
        """
        **[Required]** Gets the metastore_id of this OfflineConfig.
        Hive metastore identifier.


        :return: The metastore_id of this OfflineConfig.
        :rtype: str
        """
        return self._metastore_id

    @metastore_id.setter
    def metastore_id(self, metastore_id):
        """
        Sets the metastore_id of this OfflineConfig.
        Hive metastore identifier.


        :param metastore_id: The metastore_id of this OfflineConfig.
        :type: str
        """
        self._metastore_id = metastore_id

    def __repr__(self):
        return formatted_flat_dict(self)

    def __eq__(self, other):
        if other is None:
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        return not self == other
