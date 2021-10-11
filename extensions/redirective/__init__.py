from typing import Dict, Any, List, Tuple

from docutils import nodes
from sphinx.application import Sphinx
from sphinx.environment import BuildEnvironment
from sphinx.util import logging
from sphinx.util.docutils import SphinxDirective

# Sphinx logger
logger = logging.getLogger(__name__)


class RedirectiveNode(nodes.General, nodes.Element):
    redirect_list: List[str] = list()

    def __init__(self, redirects: List[str]):
        super().__init__()
        self.redirect_list = redirects.copy()
        # logger.info('RedirectiveNode: redirect_list=%s' % ','.join(self.redirect_list))

    def astext(self) -> str:
        return ','.join(self.redirect_list)

    def get_list(self) -> List[str]:
        return self.redirect_list


class Redirective(SphinxDirective):
    has_content = True

    def run(self) -> List[nodes.Node]:
        redirects: List[str] = list()
        for line in self.content.data:
            redirects.append('%s' % line)
        # logger.info('directive: redirects=%s' % ','.join(redirects))
        return [RedirectiveNode(redirects)]


class DoctreeWalker(nodes.SparseNodeVisitor):
    section_redirects: Dict[str, List[str]]
    root_section: str

    def __init__(self, document: nodes.document):
        super().__init__(document)
        self.section_redirects = dict()
        self.root_section = ''
        self.find_root_section(document)

    def find_root_section(self, document: nodes.document):
        for child in document.children:
            if isinstance(child, nodes.section):
                # logger.info('found section')
                for attr in child.attlist():
                    if attr[0] == 'ids':
                        self.root_section = attr[1][0]
                        break

    def visit_section(self, node: nodes.section):
        # get section id
        section_id: str = ''
        for att in node.attlist():
            if att[0] == 'ids':
                # TODO: Should this assumption be allowed?
                section_id = att[1][0]
                break
        # logger.info('  > section: %s' % section_id)
        # look for redirective nodes; remove them when we're done
        redirects: List[str] = list()
        for child in node.children:
            if isinstance(child, RedirectiveNode):
                redir_node: RedirectiveNode = child
                # logger.info('child is RedirectiveNode; list=%s' % ','.join(redir_node.get_list()))
                redirects.extend(redir_node.get_list())
                child.replace_self([])
        if len(redirects) > 0:
            if section_id != '':
                # logger.info('section_redirects[%s] = %s' % (section_id, ','.join(redirects)))
                self.section_redirects[section_id] = redirects

    def unknown_visit(self, node: nodes.Node) -> Any:
        raise nodes.SkipNode

    def get_redirects(self) -> Dict[str, List[str]]:
        return self.section_redirects

    def get_root_section(self) -> str:
        return self.root_section


def setup(app: Sphinx) -> Dict[str, Any]:
    """
    Sphinx extension setup function.

    :param app: The Sphinx Application instance
    :return: A dict of Sphinx extension options
    """
    app.add_directive('redirective', Redirective)
    app.add_node(RedirectiveNode)
    app.connect('env-purge-doc', env_purge_doc)
    app.connect('env-merge-info', env_merge_info)
    app.connect('html-collect-pages', html_collect_pages)
    app.connect('doctree-resolved', doctree_resolved)
    return {
        'version': '0.1',
        'parallel_read_safe': True,
        'parallel_write_safe': True,
    }


def env_purge_doc(app: Sphinx, env: BuildEnvironment, docname: str) -> None:
    """
    Purge an existing document from the pickled document list.
    This function is called when the Sphinx `env-purge-doc` event is fired.

    :param app: The Sphinx instance; unused
    :param env: The Sphinx BuildEnvironment
    :param docname: The name of the document to purge
    """
    if hasattr(env, 'redirective_redirects'):
        if docname in env.redirective_redirects:
            logger.info('env_purge_doc: redirects contains %s; removing it' % docname)
            env.redirective_redirects.pop(docname)


def env_merge_info(app: Sphinx, env: BuildEnvironment, docnames: List[str], other: BuildEnvironment) -> None:
    """
    Merge collected document names from parallel readers (workers) into the master Sphinx environment.
    This function is called when the Sphinx `env-merge-info` event is fired.

    :param app: The Sphinx Application instance
    :param env: The master Sphinx BuildEnvironment
    :param docnames: A list of the document names to merge
    :param other: The Sphinx BuildEnvironment from the reader worker
    """
    if not hasattr(env, 'redirective_redirects'):
        env.redirective_redirects = dict()
    # Add any links that were present in the reader worker's environment
    if hasattr(other, 'redirective_redirects'):
        for linkKey in other.redirective_redirects:
            if linkKey in env.redirective_redirects:
                env.redirective_redirects[linkKey].extend(other.redirective_redirects[linkKey])
            else:
                env.redirective_redirects[linkKey] = other.redirective_redirects[linkKey]


def html_collect_pages(app: Sphinx) -> List[Tuple[str, Dict[str, Any], str]]:
    """
    Collect the redirect page files.

    :param app: The Sphinx Application instance
    :return: A list of redirect pages to create
    """
    redirect_pages: List[Tuple[str, Dict[str, Any], str]] = list()
    if hasattr(app.env, 'redirective_redirects'):
        # get html_baseurl
        html_baseurl = ''
        if app.config.html_baseurl != '':
            html_baseurl = app.config.html_baseurl
        # return an entry for each redirect page to write
        for redir_from in app.env.redirective_redirects:
            for redir_to in app.env.redirective_redirects[redir_from]:
                # to_uri = '%s/%s' % (html_baseurl, redir_to)
                to_uri = html_baseurl
                if not html_baseurl.endswith('/'):
                    to_uri += '/'
                if '#' in str(redir_to):
                    toks: List[str] = str(redir_to).split('#')
                    if len(toks) == 1:
                        to_uri += '%s.html' % toks[0]
                    elif len(toks) >= 2:
                        to_uri += '%s.html#%s' % (toks[0], toks[1])
                    else:
                        to_uri += '%s.html' % redir_to
                else:
                    to_uri += '%s.html' % redir_to
                logger.info("redirective: %s -> %s" % (redir_from, to_uri))
                redirect_pages.append((redir_from,
                                       {
                                           'title': 'redirecting...',
                                           'to_uri': to_uri,
                                       },
                                       'redirective.html'))
    return redirect_pages


def doctree_resolved(app: Sphinx, doctree: nodes.document, docname: str) -> None:
    # if docname != 'configure/configuration-settings':
    #     return
    # logger.info('docname: %s' % docname)
    walker: DoctreeWalker = DoctreeWalker(doctree)
    doctree.walk(walker)
    section_redirects: Dict[str, List[str]] = walker.get_redirects()
    if len(section_redirects) == 0:
        return
    if not hasattr(app.env, 'redirective_redirects'):
        app.env.redirective_redirects = dict()
    for section_id in section_redirects:
        # from: section_redirects[section_id]...
        for sec_redir in section_redirects[section_id]:
            redirect_from = sec_redir
            # to: docname + '#' + section_id
            if section_id == walker.get_root_section():
                redirect_to = docname
            else:
                redirect_to = '%s#%s' % (docname, section_id)
            # logger.info(' >> %s' % redirect_to)
            if redirect_from in app.env.redirective_redirects:
                app.env.redirective_redirects[redirect_from].append(redirect_to)
            else:
                app.env.redirective_redirects[redirect_from] = [redirect_to]
