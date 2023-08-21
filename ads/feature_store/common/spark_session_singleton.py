#!/usr/bin/env python
# -*- coding: utf-8; -*-
import copy

import ads

# Copyright (c) 2023 Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/

from ads.common.decorator.runtime_dependency import OptionalDependency
import os
from ads.common.oci_client import OCIClientFactory

try:
    from delta import configure_spark_with_delta_pip
except ModuleNotFoundError:
    raise ModuleNotFoundError(
        f"The `pyspark` module was not found. Please run `pip install "
        f"{OptionalDependency.SPARK}`."
    )
except Exception as e:
    raise
try:
    from pyspark.sql import SparkSession
except ModuleNotFoundError:
    raise ModuleNotFoundError(
        f"The `pyspark` module was not found. Please run `pip install "
        f"{OptionalDependency.SPARK}`."
    )
except Exception as e:
    raise


def get_env_bool(env_var: str, default: bool = False) -> bool:
    """
    :param env_var: Environment variable name
    :param default: Default environment variable value
    :return: Value of the boolean env variable
    """
    env_val = os.getenv(env_var)
    if env_val is None:
        env_val = default
    else:
        env_val = env_val.lower()
        if env_val == "true":
            env_val = True
        elif env_val == "false":
            env_val = False
        else:
            raise ValueError(
                "For environment variable: {0} only string values T/true or F/false are allowed but: \
                {1} was provided.".format(
                    env_var, env_val
                )
            )
    return env_val


def developer_enabled():
    return get_env_bool("DEVELOPER_MODE", False)


def redis_path():
    return os.getenv("REDIS_PATH")


class SingletonMeta(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class SparkSessionSingleton(metaclass=SingletonMeta):
    """Class provides the spark session."""

    def __init__(self, metastore_id: str = None):
        """Virtually private constructor."""

        spark_builder = (
            SparkSession.builder.appName("FeatureStore")
            .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
            .config(
                "spark.sql.catalog.spark_catalog",
                "org.apache.spark.sql.delta.catalog.DeltaCatalog",
            )
            .enableHiveSupport()
        )

        if not developer_enabled() and metastore_id:
            # Get the authentication credentials for the OCI data catalog service
            auth = copy.copy(ads.auth.default_signer())

            # Remove the "client_kwargs" key from the authentication credentials (if present)
            auth.pop("client_kwargs", None)

            data_catalog_client = OCIClientFactory(**auth).data_catalog
            metastore = data_catalog_client.get_metastore(metastore_id).data
            # Configure the Spark session builder object to use the specified metastore
            spark_builder.config(
                "spark.hadoop.oracle.dcat.metastore.id", metastore_id
            ).config(
                "spark.sql.warehouse.dir", metastore.default_managed_table_location
            ).config(
                "spark.driver.memory", "16G"
            )
        # if not developer_enabled() and redis_id:

        if developer_enabled():
            # Configure spark session with delta jars only in developer mode. In other cases,
            # jars should be part of the conda pack
            # redis_host = "localhost"
            # spark_builder.config("spark.jars", redis_path())\
            #     .config("spark.redis.host", redis_host)\
            #     .config("spark.redis.port", "6379")
            my_packages = ['org.apache.spark:spark-avro_2.12:3.2.1','org.apache.spark:spark-sql-kafka-0-10_2.12:3.2.1','com.oracle.oci.sdk:oci-java-sdk-addons-sasl:2.45.0']
            # spark_builder.config('spark.jars.packages',
            #                      'org.apache.spark:spark-avro_2.12:3.2.1,'
            #                      + 'org.apache.spark:spark-sql-kafka-0-10_2.12:3.2.1,'
            #                      + 'com.oracle.oci.sdk:oci-java-sdk-addons-sasl:2.45.0')
            self.spark_session = configure_spark_with_delta_pip(
                spark_builder, my_packages
            ).getOrCreate()
        else:
            self.spark_session = spark_builder.getOrCreate()

        self.spark_session.conf.set("spark.sql.execution.arrow.pyspark.enabled", "true")
        self.spark_session.sparkContext.setLogLevel("OFF")

    def get_spark_session(self):
        """Access method to get the spark session."""
        return self.spark_session
