import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="rescue_loader",
    version="2018.12.31.2",
    author="Po Yen Cheng",
    author_email="po.cheng@technexion.com",
    description="Rescue Loader Python Scripts Package",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/TechNexion/rescue_loader",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: MIT License",
        "Operating System :: OS Independent",
    ],
)
