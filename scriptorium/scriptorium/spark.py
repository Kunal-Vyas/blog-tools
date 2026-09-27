from pyspark.sql import SparkSession


def session(name: str) -> SparkSession:
    """Local mode unless spark-submit has already chosen a master."""
    return (SparkSession.builder.appName(name)
            .config("spark.sql.shuffle.partitions", "8")
            .config("spark.ui.showConsoleProgress", "false")
            .getOrCreate())
