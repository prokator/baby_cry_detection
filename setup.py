from setuptools import setup, find_packages

setup(
    name='baby_cry_detection',
    version='1.1',
    description='Classification of signals to detect baby cry',
    url="https://github.com/giulbia/baby_cry_detection.git",
    author='Giulia Bianchi',
    author_email="gbianchi@xebia.fr",
    license='new BSD',
    packages=find_packages(),
    install_requires=['numpy', 'librosa', 'requests'],
    tests_require=['pytest', "unittest2"],
    entry_points={
        'console_scripts': [
            'baby-cry-monitor=baby_cry_detection.monitor.cli:main',
            'baby-cry-api=baby_cry_detection.monitor.api:main',
        ],
    },
    scripts=[],
    py_modules=["baby_cry_detection"],
    include_package_data=True,
    zip_safe=False
)
