"""Toolkit for interacting with Spark SQL."""
from typing import List

from ads.feature_store.spark_sql.tool.tool import QuerySparkSQLTool, InfoSparkSQLTool, ListSparkSQLTablesTool, \
    QueryCheckerTool, ListSparkSQLDatabasesTool
from langchain_core.language_models import BaseLanguageModel
from langchain_core.pydantic_v1 import Field

from langchain.agents.agent_toolkits.base import BaseToolkit
from langchain.tools import BaseTool

from ads.feature_store.spark_sql.utilities.spark_sql import SparkSQL


class SparkSQLToolkit(BaseToolkit):
    """Toolkit for interacting with Spark SQL."""

    db: SparkSQL = Field(exclude=True)
    llm: BaseLanguageModel = Field(exclude=True)

    class Config:
        """Configuration for this pydantic object."""

        arbitrary_types_allowed = True

    def get_tools(self) -> List[BaseTool]:
        """Get the tools in the toolkit."""
        return [
            QuerySparkSQLTool(db=self.db),
            InfoSparkSQLTool(db=self.db),
            ListSparkSQLTablesTool(db=self.db),
            ListSparkSQLDatabasesTool(db=self.db),
            QueryCheckerTool(db=self.db, llm=self.llm),
        ]
