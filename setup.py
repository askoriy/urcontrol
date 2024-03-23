from setuptools import setup, find_packages

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name='urcontrol',
    version='0.0.1',
    author='Oleksandr Skoryi',
    author_email='al.skoriy@gmail.com',
    description='Command-line tool to control the Steinberg UR44C Mixer and DSP',
    long_description=long_description,
    long_description_content_type="text/markdown",
    license='MIT',
    url='https://github.com/askoriy/urcontrol',
    packages=find_packages(),
    py_modules=['urcontrol'],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    entry_points={
        'console_scripts': [
            'urcontrol = urcontrol:main',
        ],
    },
    install_requires=[
        'python-rtmidi>=1.5.8'
    ],
)
