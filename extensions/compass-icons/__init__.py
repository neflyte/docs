"""
compass-icons - a Sphinx extension that adds the ability to display Compass Icons using a directive or a role

examples:

1. Role:

   ```rst
   :compass-icon:`icon-name,Icon Description`
   ```

2. Directive:

   ```rst
   .. compass-icon:: icon-name
     :description: Icon Description
   ```
"""
from docutils import nodes
from docutils.nodes import NodeVisitor
from docutils.parsers.rst.directives import unchanged
from docutils.parsers.rst.states import Inliner
from sphinx.application import Sphinx
from sphinx.util.docutils import SphinxDirective
from typing import Dict, Any, List, Tuple


DIRECTIVE_NAME = "compass-icon"
OPTION_DESCRIPTION = "description"


def setup(app: Sphinx) -> Dict[str, Any]:
    app.add_directive(DIRECTIVE_NAME, CompassIconDirective)
    app.add_node(CompassIconContainer, html=(visit, depart))
    app.add_role(DIRECTIVE_NAME, compass_icon_role)
    return {
        "version": "0.1.0",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }


class CompassIconContainer(nodes.Element):
    tagname = "span"
    icon_name: str = ""
    icon_description: str = ""

    def __init__(self, name: str, description: str = ""):
        super().__init__()
        self.icon_name = name
        if description != "":
            self.icon_description = description


def visit(visitor: NodeVisitor, node: CompassIconContainer):
    node_attributes = node.attributes.copy()
    node_attributes.pop("classes")
    node_attributes.pop("backrefs")
    node_attributes.pop("names")
    node_attributes.pop("dupnames")
    node_attributes["class"] = node.icon_name
    node_attributes["role"] = "image"
    node_attributes["aria-label"] = node.icon_description
    node_attributes["title"] = node.icon_description
    text = visitor.starttag(node, node.tagname, **node_attributes)
    visitor.body.append(text.strip())


def depart(visitor: NodeVisitor, node: CompassIconContainer):
    visitor.body.append(f"</{node.tagname}>")


def compass_icon_role(
    name: str, rawtext: str, text: str, lineno: int,
    inliner: Inliner, options: Dict = None, content: List = None
) -> Tuple[List[nodes.Node], List[nodes.system_message]]:
    icon_name = ""
    icon_description = ""
    tokens = text.split(',', 1)
    if len(tokens) == 2:
        icon_name = tokens[0]
        icon_description = tokens[1]
    elif len(tokens) == 1:
        icon_name = tokens[0]
    return [CompassIconContainer(icon_name, icon_description)], list()


class CompassIconDirective(SphinxDirective):
    has_content = False
    required_arguments = 1
    final_argument_whitespace = True
    option_spec = {
        OPTION_DESCRIPTION: unchanged
    }

    def run(self) -> List[nodes.Node]:
        icon_name = self.arguments[0]
        icon_description = ""
        if OPTION_DESCRIPTION in self.options:
            icon_description = self.options[OPTION_DESCRIPTION]
        return [CompassIconContainer(icon_name, icon_description)]
