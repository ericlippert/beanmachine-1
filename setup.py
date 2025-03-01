# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import os
import platform
import re
import sys
from glob import glob

from pybind11.setup_helpers import build_ext, Pybind11Extension
from setuptools import find_packages, setup


REQUIRED_MAJOR = 3
REQUIRED_MINOR = 7

INSTALL_REQUIRES = [
    "arviz>=0.12.1",
    "astor>=0.7.1",
    "black==22.3.0",
    "botorch>=0.5.1",
    "gpytorch>=1.3.0, <1.9.0",
    "graphviz>=0.17",
    "netCDF4<=1.5.8; python_version<'3.8'",
    "numpy>=1.18.1",
    "pandas>=0.24.2",
    "plotly>=2.2.1",
    "scipy>=0.16",
    "statsmodels>=0.12.0",
    "torch>=1.9.0",
    "tqdm>=4.46.0",
    "typing-extensions>=3.10",
    "xarray>=0.16.0",
]
TEST_REQUIRES = ["pytest>=7.0.0", "pytest-cov"]
TUTORIALS_REQUIRES = [
    "bokeh",
    "cma",
    "ipywidgets",
    "jupyter",
    "lxml>=4.9",
    "matplotlib",
    "mdformat",
    "mdformat-myst",
    "scikit-learn>=1.0.0",
    "seaborn",
    "tabulate",
    "torchvision",
]
DEV_REQUIRES = (
    TEST_REQUIRES
    + TUTORIALS_REQUIRES
    + [
        "flake8==4.0.1",
        "libcst==0.4.1",
        "nbval",
        "sphinx==4.2.0",
        "sphinx-autodoc-typehints",
        "sphinx_rtd_theme",
        "toml>=0.10.2",
        # `black` is included in `INSTALL_REQUIRES` above.
        "ufmt==1.3.2",
        "usort==1.0.2",
    ]
)

if platform.system() == "Windows":
    CPP_COMPILE_ARGS = ["/WX", "/permissive-", "/std:c++20"]
else:
    CPP_COMPILE_ARGS = ["-std=c++2a", "-Werror"]


# Check for python version
if sys.version_info < (REQUIRED_MAJOR, REQUIRED_MINOR):
    error = (
        "Your version of python ({major}.{minor}) is too old. You need "
        "python >= {required_major}.{required_minor}."
    ).format(
        major=sys.version_info.major,
        minor=sys.version_info.minor,
        required_minor=REQUIRED_MINOR,
        required_major=REQUIRED_MAJOR,
    )
    sys.exit(error)


# get version string from module
current_dir = os.path.dirname(os.path.abspath(__file__))
init_file = os.path.join(current_dir, "src", "beanmachine", "__init__.py")
version_regexp = r"__version__ = ['\"]([^'\"]*)['\"]"
with open(init_file, "r") as f:
    version = re.search(version_regexp, f.read(), re.M).group(1)

# read in README.md as the long description
with open("README.md", "r") as fh:
    long_description = fh.read()

# Use absolute path to the src directory
INCLUDE_DIRS = [os.path.join(current_dir, "src")]

# check if we're installing in a conda environment
if "CONDA_PREFIX" in os.environ:
    conda_inc = "Library/include" if platform.system() == "Windows" else "include"
    conda_include_dir = os.path.join(os.environ["CONDA_PREFIX"], conda_inc)
    INCLUDE_DIRS.extend([conda_include_dir, os.path.join(conda_include_dir, "eigen3")])
    INCLUDE_DIRS.extend([conda_include_dir, os.path.join(conda_include_dir, "boost")])

if sys.platform.startswith("linux"):
    INCLUDE_DIRS.extend(
        [
            "/usr/include",
            "/usr/include/eigen3",
            "/usr/include/boost169/",
            "/usr/include/x86_64-linux-gnu",
        ]
    )
elif sys.platform.startswith("darwin"):
    # MacOS dependencies installed through HomeBrew
    INCLUDE_DIRS.extend(
        glob("/usr/local/Cellar/eigen/*/include/eigen3")
        + glob("/usr/local/Cellar/boost/*/include")
    )

# Add range-v3 'include' directory to configuration
RANGE_V3_INCLUDE_DIR_CANDIDATES = [
    c for c in [os.environ.get("RANGE_V3_INCLUDE_DIR")] if c is not None
]
if sys.platform.startswith("linux"):
    RANGE_V3_INCLUDE_DIR_CANDIDATES.extend(
        [
            os.path.join(current_dir, "vcpkg/packages/range-v3_x64-linux/include"),
            "/usr/include/range-v3",
        ]
    )
elif sys.platform.startswith("darwin"):
    RANGE_V3_INCLUDE_DIR_CANDIDATES.extend(
        [
            os.path.join(current_dir, "vcpkg/packages/range-v3_x64-osx/include"),
            *glob("/usr/local/Cellar/range-v3/*/include"),  # Homebrew
        ]
    )
elif platform.system() == "Windows":
    RANGE_V3_INCLUDE_DIR_CANDIDATES.extend(
        [
            os.path.join(current_dir, "vcpkg/packages/range-v3_x86-windows/include"),
            # The following option was observed being used on GitHub Actions runner:
            "C:/vcpkg/packages/range-v3_x86-windows/include",
        ]
    )
print(
    "Checking directories for range-v3 'include':\n",
    "\n".join(RANGE_V3_INCLUDE_DIR_CANDIDATES),
)
selected_range_v3_include_dirs = [
    candidate
    for candidate in RANGE_V3_INCLUDE_DIR_CANDIDATES
    if os.path.isdir(candidate)
]
print(
    "Existing candidate directories for range-v3 'include':\n",
    "\n".join(selected_range_v3_include_dirs),
)
if len(selected_range_v3_include_dirs) == 0:
    if os.environ.get("RANGE_V3_INCLUDE_DIR"):
        message = (
            "Could not find 'include' directory for range-v3 library dependency "
            + f"either at {os.environ.get('RANGE_V3_INCLUDE_DIR')}\n"
            + "as indicated in environment variable RANGE_V3_INCLUDE_DIR, "
            + "nor in some other common locations.\n"
            + "Please make sure library is installed (see README.md) and "
            + "set RANGE_V3_INCLUDE_DIR environment variable to the right directory."
        )
    else:
        message = (
            "Could not find 'include' directory for range-v3 library dependency "
            + "in some common locations.\n"
            + "Please make sure library is installed (see README.md). "
            + "You can also manually indicate the correct 'include' directory by "
            + "setting the environment variable RANGE_V3_INCLUDE_DIR environment "
            + "variable to the right directory."
        )
        message += "Here are the directories we checked:\n " + "\n".join(
            RANGE_V3_INCLUDE_DIR_CANDIDATES
        )
    sys.exit(message)
else:
    print(
        "Using the following directory for range-v3 'include':\n",
        selected_range_v3_include_dirs[0],
    )
    INCLUDE_DIRS.append(selected_range_v3_include_dirs[0])

setup(
    name="beanmachine",
    version=version,
    description="Probabilistic Programming Language for Bayesian Inference",
    author="Meta Platforms, Inc.",
    license="MIT",
    url="https://beanmachine.org",
    project_urls={
        "Documentation": "https://beanmachine.org",
        "Source": "https://github.com/facebookresearch/beanmachine",
    },
    keywords=[
        "Probabilistic Programming Language",
        "Bayesian Inference",
        "Statistical Modeling",
        "MCMC",
        "Variational Inference",
        "PyTorch",
    ],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Programming Language :: Python :: 3 :: Only",
        "License :: OSI Approved :: MIT License",
        "Topic :: Scientific/Engineering",
        "Intended Audience :: Science/Research",
        "Intended Audience :: Developers",
    ],
    long_description=long_description,
    long_description_content_type="text/markdown",
    python_requires=">={}.{}".format(REQUIRED_MAJOR, REQUIRED_MINOR),
    install_requires=INSTALL_REQUIRES,
    packages=find_packages("src"),
    package_dir={"": "src"},
    package_data={"beanmachine/ppl": ["py.typed"]},
    ext_modules=[
        Pybind11Extension(
            name="beanmachine.graph",
            sources=sorted(
                set(glob("src/beanmachine/graph/**/*.cpp", recursive=True))
                - set(glob("src/beanmachine/graph/**/*_test.cpp", recursive=True))
            ),
            include_dirs=INCLUDE_DIRS,
            extra_compile_args=CPP_COMPILE_ARGS,
        )
    ],
    cmdclass={"build_ext": build_ext},
    extras_require={
        "dev": DEV_REQUIRES,
        "test": TEST_REQUIRES,
        "tutorials": TUTORIALS_REQUIRES,
    },
)
