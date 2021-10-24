from typing import Dict, Any, List, Tuple

from docutils import nodes
from sphinx.application import Sphinx
from sphinx.environment import BuildEnvironment
from sphinx.util import logging
from sphinx.util.docutils import SphinxDirective

# Sphinx logger
logger = logging.getLogger(__name__)


class RedirectiveNode(nodes.Element):
    def __init__(self, redirects: List[str]):
        super().__init__()
        self._redirect_list: List[str] = list()
        for redirect in redirects.copy():
            if redirect != "":
                logger.verbose("[Redirective] RedirectiveNode: adding redirect: %s" % redirect)
                self._redirect_list.append(redirect)

    def astext(self) -> str:
        return ",".join(self.redirect_list)

    @property
    def redirect_list(self) -> List[str]:
        return self._redirect_list


class Redirective(SphinxDirective):
    has_content = False
    required_arguments = 1
    final_argument_whitespace = True

    def run(self) -> List[nodes.Node]:
        redirect_args = " ".join(self.arguments)
        redirects = redirect_args.split(" ")
        logger.verbose("[Redirective] Directive: parsed redirects: %s" % ",".join(redirects))
        return [RedirectiveNode(redirects)]


class DoctreeWalker(nodes.SparseNodeVisitor):
    def __init__(self, document: nodes.document):
        super().__init__(document)
        self._section_redirects: Dict[str, List[str]] = dict()
        self._root_section: str = ""
        self.find_root_section(document)

    def find_root_section(self, document: nodes.document):
        for child in document.children:
            if isinstance(child, nodes.section):
                for attr in child.attlist():
                    if attr[0] == "ids":
                        self._root_section = attr[1][0]
                        logger.debug(
                            "[Redirective] DoctreeWalker: found root section: %s"
                            % self._root_section
                        )
                        break

    def visit_section(self, node: nodes.section):
        # get section id
        section_id: str = ""
        for att in node.attlist():
            if att[0] == "ids":
                # TODO: Should this assumption be allowed?
                section_id = att[1][0]
                if section_id != "":
                    logger.debug(
                        "[Redirective] DoctreeWalker: visiting section %s"
                        % section_id
                    )
                break
        # look for redirective nodes; remove them when we're done
        redirects: List[str] = list()
        for child in node.children:
            if isinstance(child, RedirectiveNode):
                redir_node: RedirectiveNode = child
                redirects.extend(redir_node.redirect_list)
                logger.debug(
                    "[Redirective] DoctreeWalker: child node redirects: %s"
                    % ",".join(redir_node.redirect_list)
                )
                child.replace_self([])
                break
        if len(redirects) > 0 and section_id != "":
            logger.debug(
                "[Redirective] DoctreeWalker: adding %d redirects to section %s"
                % (len(redirects), section_id)
            )
            self._section_redirects[section_id] = redirects

    def unknown_visit(self, node: nodes.Node) -> Any:
        raise nodes.SkipNode

    @property
    def section_redirects(self) -> Dict[str, List[str]]:
        return self._section_redirects

    @property
    def root_section(self) -> str:
        return self._root_section


def setup(app: Sphinx) -> Dict[str, Any]:
    """
    Sphinx extension setup function.

    :param app: The Sphinx Application instance
    :return: A dict of Sphinx extension options
    """
    app.add_directive("redirective", Redirective)
    app.add_node(RedirectiveNode)
    app.connect("env-purge-doc", env_purge_doc)
    app.connect("env-merge-info", env_merge_info)
    app.connect("html-collect-pages", html_collect_pages)
    app.connect("doctree-resolved", doctree_resolved)
    return {
        "version": "0.1",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }


def env_purge_doc(app: Sphinx, env: BuildEnvironment, docname: str) -> None:
    """
    Purge an existing document from the pickled document list.
    This function is called when the Sphinx `env-purge-doc` event is fired.

    :param app: The Sphinx instance; unused
    :param env: The Sphinx BuildEnvironment
    :param docname: The name of the document to purge
    """
    if hasattr(env, "redirective_redirects"):
        if docname in env.redirective_redirects:
            logger.verbose("[Redirective] env_purge_doc: redirects contains %s; removing it" % docname)
            env.redirective_redirects.pop(docname)


def env_merge_info(
    app: Sphinx, env: BuildEnvironment, docnames: List[str], other: BuildEnvironment
) -> None:
    """
    Merge collected document names from parallel readers (workers) into the master Sphinx environment.
    This function is called when the Sphinx `env-merge-info` event is fired.

    :param app: The Sphinx Application instance
    :param env: The master Sphinx BuildEnvironment
    :param docnames: A list of the document names to merge
    :param other: The Sphinx BuildEnvironment from the reader worker
    """
    if not hasattr(env, "redirective_redirects"):
        env.redirective_redirects = dict()
    # Add any links that were present in the reader worker's environment
    if hasattr(other, "redirective_redirects"):
        for linkKey in other.redirective_redirects:
            if linkKey in env.redirective_redirects:
                env.redirective_redirects[linkKey].extend(
                    other.redirective_redirects[linkKey]
                )
            else:
                env.redirective_redirects[linkKey] = other.redirective_redirects[
                    linkKey
                ]


def html_collect_pages(app: Sphinx) -> List[Tuple[str, Dict[str, Any], str]]:
    """
    Collect the redirect page files.

    :param app: The Sphinx Application instance
    :return: A list of redirect pages to create
    """
    redirect_pages: List[Tuple[str, Dict[str, Any], str]] = list()
    if hasattr(app.env, "redirective_redirects"):
        # get html_baseurl
        html_baseurl = ""
        if app.config.html_baseurl != "":
            html_baseurl = app.config.html_baseurl
        # return an entry for each redirect page to write
        for redir_from in app.env.redirective_redirects:
            for redir_to in app.env.redirective_redirects[redir_from]:
                # to_uri = '%s/%s' % (html_baseurl, redir_to)
                to_uri = html_baseurl
                if not html_baseurl.endswith("/"):
                    to_uri += "/"
                if "#" in str(redir_to):
                    toks: List[str] = str(redir_to).split("#")
                    if len(toks) == 1:
                        to_uri += "%s.html" % toks[0]
                    elif len(toks) >= 2:
                        to_uri += "%s.html#%s" % (toks[0], toks[1])
                    else:
                        to_uri += "%s.html" % redir_to
                else:
                    to_uri += "%s.html" % redir_to
                logger.verbose("[Redirective] Redirecting %s to %s" % (redir_from, to_uri))
                redirect_pages.append(
                    (
                        redir_from,
                        {
                            "title": "redirecting...",
                            "to_uri": to_uri,
                        },
                        "redirective.html",
                    )
                )
    return redirect_pages


def doctree_resolved(app: Sphinx, doctree: nodes.document, docname: str) -> None:
    walker: DoctreeWalker = DoctreeWalker(doctree)
    doctree.walk(walker)
    if len(walker.section_redirects) == 0:
        return
    if not hasattr(app.env, "redirective_redirects"):
        app.env.redirective_redirects = dict()
    for section_id in walker.section_redirects:
        # from: section_redirects[section_id]...
        for redirect_from in walker.section_redirects[section_id]:
            # to: docname + '#' + section_id
            if section_id == walker.root_section:
                redirect_to = docname
            else:
                redirect_to = "%s#%s" % (docname, section_id)
            # logger.info(' >> %s' % redirect_to)
            if redirect_from in app.env.redirective_redirects:
                app.env.redirective_redirects[redirect_from].append(redirect_to)
            else:
                app.env.redirective_redirects[redirect_from] = [redirect_to]
