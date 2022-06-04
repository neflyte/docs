import html
import pickle
from importlib import import_module
from os import path
from typing import Dict, Set, Tuple, Type, IO, Any, List, Iterable, Optional

from docutils import nodes
from sphinx import package_dir
from sphinx.environment import BuildEnvironment
from sphinx.search import SearchLanguage, SearchEnglish, splitter_code, languages
from sphinx.util import jsdump

from collector import WordCollector


class IndexBuilder:
    """
    Helper class that creates a search index based on the doctrees
    passed to the `feed` method.
    """
    formats = {
        'jsdump':   jsdump,
        'pickle':   pickle
    }

    def __init__(self, env: BuildEnvironment, lang: str, options: Dict, scoring: str) -> None:
        self.env = env
        self._titles: Dict[str, str] = {}           # docname -> title
        self._filenames: Dict[str, str] = {}        # docname -> filename
        self._mapping: Dict[str, Set[str]] = {}     # stemmed word -> set(docname)
        # stemmed words in titles -> set(docname)
        self._title_mapping: Dict[str, Set[str]] = {}
        self._stem_cache: Dict[str, str] = {}       # word -> stemmed word
        self._objtypes: Dict[Tuple[str, str], int] = {}     # objtype -> index
        # objtype index -> (domain, type, objname (localized))
        self._objnames: Dict[int, Tuple[str, str, str]] = {}
        # add language-specific SearchLanguage instance
        lang_class: Type[SearchLanguage] = languages.get(lang)

        # fallback; try again with language-code
        if lang_class is None and '_' in lang:
            lang_class = languages.get(lang.split('_')[0])

        if lang_class is None:
            self.lang: SearchLanguage = SearchEnglish(options)
        elif isinstance(lang_class, str):
            module, classname = lang_class.rsplit('.', 1)
            lang_class = getattr(import_module(module), classname)
            self.lang = lang_class(options)
        else:
            # it's directly a class (e.g. added by app.add_search_language)
            self.lang = lang_class(options)

        if scoring:
            with open(scoring, 'rb') as fp:
                self.js_scorer_code = fp.read().decode()
        else:
            self.js_scorer_code = ''
        self.js_splitter_code = splitter_code

    def load(self, stream: IO, format: Any) -> None:
        """Reconstruct from frozen data."""
        if isinstance(format, str):
            format = self.formats[format]
        frozen = format.load(stream)
        # if an old index is present, we treat it as not existing.
        if not isinstance(frozen, dict) or \
                frozen.get('envversion') != self.env.version:
            raise ValueError('old format')
        index2fn = frozen['docnames']
        self._filenames = dict(zip(index2fn, frozen['filenames']))
        self._titles = dict(zip(index2fn, frozen['titles']))

        def load_terms(mapping: Dict[str, Any]) -> Dict[str, Set[str]]:
            rv = {}
            for k, v in mapping.items():
                if isinstance(v, int):
                    rv[k] = {index2fn[v]}
                else:
                    rv[k] = {index2fn[i] for i in v}
            return rv

        self._mapping = load_terms(frozen['terms'])
        self._title_mapping = load_terms(frozen['titleterms'])
        # no need to load keywords/objtypes

    def dump(self, stream: IO, format: Any) -> None:
        """Dump the frozen index to a stream."""
        if isinstance(format, str):
            format = self.formats[format]
        format.dump(self.freeze(), stream)

    def get_objects(self, fn2index: Dict[str, int]) -> Dict[str, List[Tuple[int, int, int, str, str]]]:
        rv: Dict[str, List[Tuple[int, int, int, str, str]]] = {}
        otypes = self._objtypes
        onames = self._objnames
        for domainname, domain in sorted(self.env.domains.items()):
            for fullname, dispname, type, docname, anchor, prio in sorted(domain.get_objects()):
                if docname not in fn2index:
                    continue
                if prio < 0:
                    continue
                fullname = html.escape(fullname)
                dispname = html.escape(dispname)
                prefix, _, name = dispname.rpartition('.')
                plist = rv.setdefault(prefix, [])
                try:
                    typeindex = otypes[domainname, type]
                except KeyError:
                    typeindex = len(otypes)
                    otypes[domainname, type] = typeindex
                    otype = domain.object_types.get(type)
                    if otype:
                        # use str() to fire translation proxies
                        onames[typeindex] = (domainname, type,
                                             str(domain.get_type_name(otype)))
                    else:
                        onames[typeindex] = (domainname, type, type)
                if anchor == fullname:
                    shortanchor = ''
                elif anchor == type + '-' + fullname:
                    shortanchor = '-'
                else:
                    shortanchor = anchor
                plist.append((fn2index[docname], typeindex, prio, shortanchor, name))
        return rv

    def get_terms(self, fn2index: Dict) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
        rvs: Tuple[Dict[str, List[str]], Dict[str, List[str]]] = ({}, {})
        for rv, mapping in zip(rvs, (self._mapping, self._title_mapping)):
            for k, v in mapping.items():
                if len(v) == 1:
                    fn, = v
                    if fn in fn2index:
                        rv[k] = fn2index[fn]
                else:
                    rv[k] = sorted([fn2index[fn] for fn in v if fn in fn2index])
        return rvs

    def freeze(self) -> Dict[str, Any]:
        """Create a usable data structure for serializing."""
        docnames, titles = zip(*sorted(self._titles.items()))
        filenames = [self._filenames.get(docname) for docname in docnames]
        fn2index = {f: i for (i, f) in enumerate(docnames)}
        terms, title_terms = self.get_terms(fn2index)

        objects = self.get_objects(fn2index)  # populates _objtypes
        objtypes = {v: k[0] + ':' + k[1] for (k, v) in self._objtypes.items()}
        objnames = self._objnames
        return dict(docnames=docnames, filenames=filenames, titles=titles, terms=terms,
                    objects=objects, objtypes=objtypes, objnames=objnames,
                    titleterms=title_terms, envversion=self.env.version)

    def label(self) -> str:
        return "%s (code: %s)" % (self.lang.language_name, self.lang.lang)

    def prune(self, docnames: Iterable[str]) -> None:
        """Remove data for all docnames not in the list."""
        new_titles = {}
        new_filenames = {}
        for docname in docnames:
            if docname in self._titles:
                new_titles[docname] = self._titles[docname]
                new_filenames[docname] = self._filenames[docname]
        self._titles = new_titles
        self._filenames = new_filenames
        for wordnames in self._mapping.values():
            wordnames.intersection_update(docnames)
        for wordnames in self._title_mapping.values():
            wordnames.intersection_update(docnames)

    def feed(self, docname: str, filename: str, title: str, doctree: nodes.document) -> None:
        """Feed a doctree to the index."""
        self._titles[docname] = title
        self._filenames[docname] = filename

        visitor = WordCollector(doctree, self.lang)
        doctree.walk(visitor)

        # memoize self.lang.stem
        def stem(word: str) -> str:
            try:
                return self._stem_cache[word]
            except KeyError:
                self._stem_cache[word] = self.lang.stem(word).lower()
                return self._stem_cache[word]
        _filter = self.lang.word_filter

        for word in visitor.found_title_words:
            stemmed_word = stem(word)
            if _filter(stemmed_word):
                self._title_mapping.setdefault(stemmed_word, set()).add(docname)
            elif _filter(word): # stemmer must not remove words from search index
                self._title_mapping.setdefault(word, set()).add(docname)

        for word in visitor.found_words:
            stemmed_word = stem(word)
            # again, stemmer must not remove words from search index
            if not _filter(stemmed_word) and _filter(word):
                stemmed_word = word
            already_indexed = docname in self._title_mapping.get(stemmed_word, set())
            if _filter(stemmed_word) and not already_indexed:
                self._mapping.setdefault(stemmed_word, set()).add(docname)

    def context_for_searchtool(self) -> Dict[str, Any]:
        if self.lang.js_splitter_code:
            js_splitter_code = self.lang.js_splitter_code
        else:
            js_splitter_code = self.js_splitter_code

        return {
            'search_language_stemming_code': self.get_js_stemmer_code(),
            'search_language_stop_words': jsdump.dumps(sorted(self.lang.stopwords)),
            'search_scorer_tool': self.js_scorer_code,
            'search_word_splitter_code': js_splitter_code,
        }

    def get_js_stemmer_rawcodes(self) -> List[str]:
        """Returns a list of non-minified stemmer JS files to copy."""
        if self.lang.js_stemmer_rawcode:
            return [
                path.join(package_dir, 'search', 'non-minified-js', fname)
                for fname in ('base-stemmer.js', self.lang.js_stemmer_rawcode)
            ]
        else:
            return []

    def get_js_stemmer_rawcode(self) -> Optional[str]:
        return None

    def get_js_stemmer_code(self) -> str:
        """Returns JS code that will be inserted into language_data.js."""
        if self.lang.js_stemmer_rawcode:
            js_dir = path.join(package_dir, 'search', 'minified-js')
            with open(path.join(js_dir, 'base-stemmer.js')) as js_file:
                base_js = js_file.read()
            with open(path.join(js_dir, self.lang.js_stemmer_rawcode)) as js_file:
                language_js = js_file.read()
            return ('%s\n%s\nStemmer = %sStemmer;' %
                    (base_js, language_js, self.lang.language_name))
        else:
            return self.lang.js_stemmer_code
