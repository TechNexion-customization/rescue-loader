import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="rescue_loader",
    version="2020.06.30.1",
    author="Po Yen Cheng",
    author_email="po.cheng@technexion.com",
    description="Rescue Loader Python Scripts Package",
    long_description=long_description,
    url="https://github.com/TechNexion/rescue-loader.git",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: MIT License",
        "Operating System :: OS Independent",
    ],
)
