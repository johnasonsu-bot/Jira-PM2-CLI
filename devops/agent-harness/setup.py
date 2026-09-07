from setuptools import setup, find_namespace_packages

setup(
    name='cli-anything-devops', version='0.1.0',
    description='Forge DevOps: local Jira-inspired work tracking and HTTP CLI-Anything harness',
    packages=find_namespace_packages(include=['cli_anything.*']),
    python_requires='>=3.10', install_requires=['click>=8', 'prompt-toolkit>=3'],
    extras_require={'dev': ['pytest>=7'], 'mcp': ['mcp>=1.28,<2']},
    package_data={'cli_anything.devops': ['web/*', 'skills/*.md']},
    entry_points={'console_scripts': [
        'cli-anything-devops=cli_anything.devops.devops_cli:main',
        'forge-devops-server=cli_anything.devops.server:main',
        'forge-devops-mcp=cli_anything.devops.mcp_server:main',
    ]},
)
