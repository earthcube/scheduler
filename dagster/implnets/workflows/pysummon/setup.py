from setuptools import find_packages, setup

setup(
    name="pysummon",
    packages=find_packages(exclude=["pysummon_tests"]),
    install_requires=[
        "dagster",
        "dagster-aws",
        "requests",
        "beautifulsoup4",
        "lxml",
        "playwright",
        "orjson",
        "pyyaml",
        # shared pure modules (jsonld_utils, steps, reporting, rdf_utils);
        # installed from ../pipeline in the same image
        "pipeline",
    ],
    extras_require={"dev": ["dagster-webserver", "pytest"]},
)
