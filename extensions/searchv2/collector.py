import re
from typing import List

from docutils import nodes
from docutils.nodes import Element, Node
from sphinx import addnodes
from sphinx.util import logging


class WordCollector(nodes.NodeVisitor):
    logger = logging.getLogger("WordCollector")
    found_words: List[str]
    found_title_words: List[str]

    def __init__(self, document: nodes.document):
        super().__init__(document)
        self.found_words = list()
        self.found_title_words = list()

    def is_meta_keywords(self, node: Element) -> bool:
        if (isinstance(node, (addnodes.meta, addnodes.docutils_meta)) and
                node.get('name') == 'keywords'):
            meta_lang = node.get('lang')
            if meta_lang is None:  # lang not specified
                return True
            elif meta_lang == self.lang.lang:  # matched to html_search_language
                return True
        return False

    def dispatch_visit(self, node: Node) -> None:
        if isinstance(node, nodes.comment):
            raise nodes.SkipNode
        elif isinstance(node, nodes.raw):
            if 'html' in node.get('format', '').split():
                # Some people might put content in raw HTML that should be searched,
                # so we just amateurishly strip HTML tags and index the remaining
                # content
                nodetext = re.sub(r'(?is)<style.*?</style>', '', node.astext())
                nodetext = re.sub(r'(?is)<script.*?</script>', '', nodetext)
                nodetext = re.sub(r'<[^<]+?>', '', nodetext)
                self.found_words.extend(self.lang.split(nodetext))
            raise nodes.SkipNode
        elif isinstance(node, nodes.Text):
            self.found_words.extend(self.lang.split(node.astext()))
        elif isinstance(node, nodes.title):
            self.found_title_words.extend(self.lang.split(node.astext()))
        elif isinstance(node, Element) and self.is_meta_keywords(node):
            keywords = node['content']
            keywords = [keyword.strip() for keyword in keywords.split(',')]
            self.found_words.extend(keywords)


