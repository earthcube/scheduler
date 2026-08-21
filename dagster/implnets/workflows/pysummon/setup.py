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
        # default fetch engine; connects over CDP or uses its HTTP-only
        # strategy, so no `crawl4ai-setup` browser download is needed
        "crawl4ai>=0.7",
        "orjson",
        "pyyaml",
        # shared pure modules (jsonld_utils, steps, reporting, rdf_utils);
        # installed from ../pipeline in the same image
        "pipeline",
    ],
    extras_require={"dev": ["dagster-webserver", "pytest"]},
)
