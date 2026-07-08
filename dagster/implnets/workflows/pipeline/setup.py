from setuptools import find_packages, setup

setup(
    name="pipeline",
    packages=find_packages(exclude=["pipeline_tests"]),
    install_requires=[
        "dagster",
        "dagster-aws",
        "dagster-docker",
        "docker",
        "pyld",
        "rdflib",
        "pandas",
        "pyyaml",
        "orjson",
    ],
    extras_require={"dev": ["dagster-webserver", "pytest"]},
)
