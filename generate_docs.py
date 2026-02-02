"""
Documentation generation script.

Generates API documentation using Sphinx.
"""

import subprocess  # nosec B404: Known safe Sphinx invocation for documentation generation
import sys
from pathlib import Path


def generate_docs():
    """Generate API documentation."""
    print("Generating API Documentation")

    # Check if sphinx is available
    try:
        import sphinx

        print(f"Using Sphinx {sphinx.__version__}")
    except ImportError:
        print("Sphinx not installed. Install with: pip install sphinx sphinx-rtd-theme")
        return False

    # Create docs directory if it doesn't exist
    docs_dir = Path("docs")
    docs_dir.mkdir(exist_ok=True)

    # Create basic Sphinx configuration
    conf_content = """
# Configuration file for the Sphinx documentation builder.

import os
import sys
sys.path.insert(0, os.path.abspath('..'))

project = 'Carbon Ops'
copyright = '2026, Carbon Ops Team'
author = 'Carbon Ops Team'

# -- General configuration ---------------------------------------------------
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.viewcode',
    'sphinx.ext.napoleon',
    'sphinx.ext.intersphinx',
    'sphinx.ext.todo',
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# -- Options for HTML output -------------------------------------------------
html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']

# -- Extension configuration --------------------------------------------------
autodoc_default_options = {
    'members': True,
    'undoc-members': True,
    'show-inheritance': True,
}
autodoc_member_order = 'bysource'

# Napoleon settings
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = False
napoleon_include_private_with_doc = False

# Intersphinx mapping
intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
}

# Todo settings
todo_include_todos = True
"""

    conf_py = docs_dir / "conf.py"
    with conf_py.open("w") as f:
        f.write(conf_content)

    # Create index.rst
    index_content = """
Carbon Ops Documentation
========================

Carbon Ops is a comprehensive toolkit for monitoring and tracking carbon emissions
in software systems, with particular focus on AI/ML workloads.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   modules
   examples

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
"""

    index_rst = docs_dir / "index.rst"
    with index_rst.open("w") as f:
        f.write(index_content)

    # Create modules.rst
    modules_content = """
API Reference
=============

.. automodule:: carbon_ops
   :members:
   :undoc-members:
   :show-inheritance:

Energy Logger
-------------

.. automodule:: carbon_ops.energy_logger
   :members:
   :undoc-members:
   :show-inheritance:

Carbon Estimator
----------------

.. automodule:: carbon_ops.carbon_estimator
   :members:
   :undoc-members:
   :show-inheritance:

Carbon Taxonomy
---------------

.. automodule:: carbon_ops.carbon_taxonomy
   :members:
   :undoc-members:
   :show-inheritance:

Configuration Loader
--------------------

.. automodule:: carbon_ops.config_loader
   :members:
   :undoc-members:
   :show-inheritance:

Tools
-----

Ledger
~~~~~~

.. automodule:: carbon_ops.tools.ledger
   :members:
   :undoc-members:
   :show-inheritance:

Verification
~~~~~~~~~~~~

.. automodule:: carbon_ops.tools.verify
   :members:
   :undoc-members:
   :show-inheritance:

Ledger Writer
~~~~~~~~~~~~~

.. automodule:: carbon_ops.ledger_writer
   :members:
   :undoc-members:
   :show-inheritance:

Canonicalize
~~~~~~~~~~~~

.. automodule:: carbon_ops.tools.canonicalize
   :members:
   :undoc-members:
   :show-inheritance:

Research
--------

Embodied Carbon Database
~~~~~~~~~~~~~~~~~~~~~~~~

.. automodule:: carbon_ops.research.embodied_carbon_db
   :members:
   :undoc-members:
   :show-inheritance:
"""

    modules_rst = docs_dir / "modules.rst"
    with modules_rst.open("w") as f:
        f.write(modules_content)

    # Create examples.rst
    examples_rst = docs_dir / "examples.rst"
    examples_rst.write_text("""
Examples
========

Basic Usage
-----------

Energy Logger Demo
~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../examples/energy_logger_demo.py
   :language: python
   :linenos:

Advanced Monitoring
~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../examples/advanced_monitoring.py
   :language: python
   :linenos:

Ledger Operations
~~~~~~~~~~~~~~~~~

.. literalinclude:: ../examples/ledger_operations.py
   :language: python
   :linenos:
""")

    # Create _static and _templates directories
    (docs_dir / "_static").mkdir(exist_ok=True)
    (docs_dir / "_templates").mkdir(exist_ok=True)

    # Generate HTML documentation
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "sphinx",
                "-b",
                "html",
                str(docs_dir),
                str(docs_dir / "_build" / "html"),
            ],
            capture_output=True,
            text=True,
            cwd=".",
            check=False,
            timeout=300,
        )  # nosec B603: command arguments are static and trusted (Sphinx build)

        if result.returncode == 0:
            print("Documentation generated successfully.")
            print(
                f"HTML docs available at: {docs_dir / '_build' / 'html' / 'index.html'}"
            )
            return True
        else:
            print("Sphinx build failed:")
            print(result.stdout)
            print(result.stderr)
            return False

    except subprocess.TimeoutExpired:
        print("Sphinx build timed out after 5 minutes")
        return False
    except FileNotFoundError:
        print(
            "Sphinx not found. Please install with: pip install sphinx sphinx-rtd-theme"
        )
        return False


if __name__ == "__main__":
    success = generate_docs()
    sys.exit(0 if success else 1)
