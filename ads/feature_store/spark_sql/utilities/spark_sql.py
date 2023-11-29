from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any, Iterable, List, Optional, Dict

from ads.feature_store.common.spark_session_singleton import SparkSessionSingleton

from ads.feature_store.feature_store import FeatureStore

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, Row, SparkSession


class SparkSQL:
    """SparkSQL is a utility class for interacting with Spark SQL."""

    def __init__(
        self,
        feature_store: FeatureStore,
        sample_rows_in_table_info: int = 3,
    ):
        """Initialize a SparkSQL object.

        Args:
            spark_session: A SparkSession object.
              If not provided, one will be created.
            catalog: The catalog to use.
              If not provided, the default catalog will be used.
            schema: The schema to use.
              If not provided, the default schema will be used.
            ignore_tables: A list of tables to ignore.
              If not provided, all tables will be used.
            include_tables: A list of tables to include.
              If not provided, all tables will be used.
            sample_rows_in_table_info: The number of rows to include in the table info.
              Defaults to 3.
        """
        self.feature_store = feature_store
        entities = self.feature_store.list_entities(compartment_id=self.feature_store.compartment_id,
                                                    feature_store_id = self.feature_store.id)
        self.database_table_map: Dict[str, List[str]] = defaultdict(lambda : [])
        self.all_tables: List[str] = []
        for entity in entities:
            # TODO: Fix this call once entity id filter is resolved
            feature_groups = entity.list_feature_group(compartment_id=self.feature_store.compartment_id, feature_store_id = self.feature_store.id, entity_id = entity.id)
            for feature_group in feature_groups:
                self.database_table_map[entity.id].append(feature_group.name)
                self.all_tables.append(f"{entity.id}.{feature_group.name}")

        try:
            from pyspark.sql import SparkSession
        except ImportError:
            raise ImportError(
                "pyspark is not installed. Please install it with `pip install pyspark`"
            )

        self._spark = SparkSessionSingleton().get_spark_session()

        self.feature_store = feature_store
        if not isinstance(sample_rows_in_table_info, int):
            raise TypeError("sample_rows_in_table_info must be an integer")

        self._sample_rows_in_table_info = sample_rows_in_table_info

    @classmethod
    def from_uri(
        cls, database_uri: str, engine_args: Optional[dict] = None, **kwargs: Any
    ) -> SparkSQL:
        """Creating a remote Spark Session via Spark connect.
        For example: SparkSQL.from_uri("sc://localhost:15002")
        """
        try:
            from pyspark.sql import SparkSession
        except ImportError:
            raise ValueError(
                "pyspark is not installed. Please install it with `pip install pyspark`"
            )

        spark = SparkSession.builder.remote(database_uri).getOrCreate()
        return cls(spark, **kwargs)

    def get_usable_table_names(self) -> Iterable[str]:
                # sorting the result can help LLM understanding it.
        return  ", ".join(self.database_table_map)

    def _get_create_table_stmt(self, table: str) -> str:
        statement = (
            self._spark.sql(f"DESCRIBE TABLE {table}").collect()
        )
        answer = "Table " + f"{table} has columns: "
        for result in statement:
            if result[0]=="":
                break
            answer += f"{result[0]} of type {result[1]}, "
        answer=answer.rstrip(", ")
        # Ignore the data source provider and options to reduce the number of tokens.
        return answer

    def get_table_info(self, table_names: Optional[List[str]] = None) -> str:
        if table_names is not None:
            missing_tables = set(table_names).difference(self.all_tables)
            if missing_tables:
                raise ValueError(f"table_names {missing_tables} not found in database")
        tables = []
        for table_name in table_names:
            table_info = self._get_create_table_stmt(table_name)
            if self._sample_rows_in_table_info:
                table_info += "\n\n/*"
                table_info += f"\n{self._get_sample_spark_rows(table_name)}\n"
                table_info += "*/"
            tables.append(table_info)
        final_str = "\n\n".join(tables)
        return final_str

    def _get_sample_spark_rows(self, table: str) -> str:
        query = f"SELECT * FROM {table} LIMIT {self._sample_rows_in_table_info}"
        df = self._spark.sql(query)
        columns_str = "\t".join(list(map(lambda f: f.name, df.schema.fields)))
        try:
            sample_rows = self._get_dataframe_results(df)
            # save the sample rows in string format
            sample_rows_str = "\n".join(["\t".join(row) for row in sample_rows])
        except Exception:
            sample_rows_str = ""

        return (
            f"{self._sample_rows_in_table_info} rows from {table} table:\n"
            f"{columns_str}\n"
            f"{sample_rows_str}"
        )

    def _convert_row_as_tuple(self, row: Row) -> tuple:
        return tuple(map(str, row.asDict().values()))

    def _get_dataframe_results(self, df: DataFrame) -> list:
        return list(map(self._convert_row_as_tuple, df.collect()))

    def run(self, command: str, fetch: str = "all") -> str:
        df = self._spark.sql(command)
        if fetch == "one":
            df = df.limit(1)
        return str(self._get_dataframe_results(df))

    def get_table_info_no_throw(self, table_names: Optional[List[str]] = None) -> str:
        """Get information about specified tables.

        Follows best practices as specified in: Rajkumar et al, 2022
        (https://arxiv.org/abs/2204.00498)

        If `sample_rows_in_table_info`, the specified number of sample rows will be
        appended to each table description. This can increase performance as
        demonstrated in the paper.
        """
        try:
            return self.get_table_info(table_names)
        except ValueError as e:
            """Format the error message"""
            return f"Error: {e}"

    def run_no_throw(self, command: str, fetch: str = "all") -> str:
        """Execute a SQL command and return a string representing the results.

        If the statement returns rows, a string of the results is returned.
        If the statement returns no rows, an empty string is returned.

        If the statement throws an error, the error message is returned.
        """
        try:
            return self.run(command, fetch)
        except Exception as e:
            """Format the error message"""
            return f"Error: {e}"
