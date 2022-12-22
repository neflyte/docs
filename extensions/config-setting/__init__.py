from docutils.nodes import Element, Node
from sphinx.addnodes import pending_xref, desc_signature, desc_name
from sphinx.application import Sphinx
from sphinx.builders import Builder
from sphinx.directives import ObjectDescription
from sphinx.domains import Domain
from sphinx.environment import BuildEnvironment
from sphinx.roles import XRefRole
from sphinx.util import logging
from sphinx.util.docutils import SphinxTranslator
from sphinx.util.nodes import make_refnode
from typing import Optional, Iterable, Tuple, List, Dict, Any

# Sphinx logger
logger = logging.getLogger(__name__)


class AnchorNode(Element):
    """
    A docutils node that writes an ``<a>`` tag that includes a specific id
    """

    anchor: str

    def __init__(self, href: str):
        super().__init__()
        self.tagname = "a"
        self.anchor = href


def visit_anchor_node(visitor: SphinxTranslator, node: AnchorNode) -> None:
    """
    Write the opening HTML tag for the anchor node
      :param visitor: The translator that handles writing HTML bodies
      :param node: The docutils node we're visiting
      :return: None
    """
    visitor.body.append('<%s id="%s">' % (node.tagname, node.anchor))


def depart_anchor_node(visitor: SphinxTranslator, node: AnchorNode) -> None:
    """
    Write the closing HTML tag for the anchor node
      :param visitor: The translator that handles writing HTML bodies
      :param node: The docutils node we're departing
      :return: None
    """
    visitor.body.append(f"</{node.tagname}>")


class ConfigSettingDirective(ObjectDescription):
    """
    A directive that allow specifying one or more terms that will be added to the search as an Object Type
    """

    has_content = False
    required_arguments = 1
    """
    The primary signature (search term) of the config setting. Used to group multiple search terms under a single
    anchor.
    """
    primary_signature = ""

    def run(self) -> List[Node]:
        anchornodes: List[Node] = list()
        sigs = self.get_signatures()
        # insert a single anchor using the first signature since we only want one anchor to represent the setting
        if len(sigs) > 0:
            if self.primary_signature == "":
                self.primary_signature = sigs[0]
            anchor = "config.setting.anchor_%s" % sigs[0]
            logger.verbose("run(): adding container for anchor %s" % anchor)
            anchornodes.append(AnchorNode(anchor))
        nodelist: List[Node] = super().run()
        anchornodes.extend(nodelist)
        return anchornodes

    def handle_signature(self, sig: str, signode: desc_signature) -> str:
        signode += desc_name(text=sig)
        return sig

    def add_target_and_index(
        self, name: str, sig: str, signode: desc_signature
    ) -> None:
        # NOTE: Don't add the anchor id to the "ids" attribute of signode; the <a> tags won't work in that case
        domain = self.env.get_domain("config")
        if isinstance(domain, ConfigSettingDomain):
            domain.add_config_setting(sig, self.primary_signature)


class ConfigSettingDomain(Domain):
    """
    A domain to hold references to individual config settings. These settings will be picked up by the Sphinx
    search and users will be given direct links to the specific setting's doc.
    """

    name = "config"
    label = "Mattermost configuration setting"
    roles = {
        "ref": XRefRole(),
    }
    directives = {
        "setting": ConfigSettingDirective,
    }
    initial_data = {
        # List[Tuple[str, str, str, str, str, int]] ==> List[Tuple[name, dispname, type, docname, anchor, priority]]
        "configs": list(),
    }

    def get_full_qualified_name(self, node: Element) -> Optional[str]:
        return "{}.{}".format("config", node.arguments[0])

    def get_objects(self) -> Iterable[Tuple[str, str, str, str, str, int]]:
        yield from self.data["configs"]

    def merge_domaindata(self, docnames: List[str], otherdata: Dict) -> None:
        self.data["configs"].extend(otherdata["configs"])

    def resolve_any_xref(
        self,
        env: BuildEnvironment,
        fromdocname: str,
        builder: Builder,
        target: str,
        node: pending_xref,
        contnode: Element,
    ) -> List[Tuple[str, Element]]:
        return list()

    def resolve_xref(
        self, env, fromdocname, builder, typ, target, node, contnode
    ) -> Optional[Node]:
        match = [
            (docname, anchor)
            for name, sig, typ, docname, anchor, prio in self.get_objects()
            if sig == target
        ]
        if len(match) > 0:
            todocname = match[0][0]
            targ = match[0][1]
            return make_refnode(builder, fromdocname, todocname, targ, contnode, targ)
        else:
            logger.warning(
                "resolve_xref(): unable to resolve crossreference; fromdocname=%s, typ=%s, target=%s"
                % (fromdocname, typ, target)
            )
            return None

    def add_config_setting(
        self, config_json_setting: str, primary_signature: str
    ) -> None:
        """
        Add a config setting to the list of config settings that the search will pick up
          :param config_json_setting: A config setting signature
          :param primary_signature: The primary signature of the config setting; ignored if empty
          :return: None
        """
        name = "config.setting_%s" % config_json_setting
        anchor_id = config_json_setting
        if primary_signature != "":
            anchor_id = primary_signature
        anchor = "config.setting.anchor_%s" % anchor_id
        config_setting = (
            name,
            config_json_setting,
            "setting",
            self.env.docname,
            anchor,
            0,
        )
        logger.verbose(
            "add_config_setting(): appending config: name=%s, dispname=%s, type=%s, docname=%s, anchor=%s, priority=%d"
            % config_setting
        )
        self.data["configs"].append(config_setting)


def setup(app: Sphinx) -> Dict[str, Any]:
    """
    Sphinx extension entry point
      :param app: The Sphinx application instance
      :return: A dict of extension options
    """
    app.add_node(AnchorNode, html=(visit_anchor_node, depart_anchor_node))
    app.add_domain(ConfigSettingDomain)
    return {
        "version": "0.1.0",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }