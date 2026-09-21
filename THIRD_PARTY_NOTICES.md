# Third-party notices

## Cytoscape.js 3.34.3

The optional local Knowledge Map downloads Cytoscape.js and its MIT license from upstream commit `716a1cb6c6015d57b674abe626deaeb5e817ee30` (release 3.34.3). This library is not authored by this repository. Copyright and permission notices are retained verbatim in `LICENSE.cytoscape` in the local asset directory and served by the viewer.

Upstream: [Cytoscape.js](https://github.com/cytoscape/cytoscape.js/tree/716a1cb6c6015d57b674abe626deaeb5e817ee30). Documentation: [js.cytoscape.org](https://js.cytoscape.org/).

| Local file | SHA-256 |
| --- | --- |
| `cytoscape.min.js` | `5f3b5b529546d5af1fc5628590af033b74511a5b6f789f5f4682845863228b91` |
| `LICENSE.cytoscape` | `eb319c6e6f233607f71e8e2f450391751883cfc0eeb3ca7ef574c13d1d9c2203` |

Installation is explicit; browsing never contacts a CDN. To update the pin, review the upstream release and license, verify both new checksums, and rerun the browser tests. Do not update the version alone or accept mismatched cached files.

SQLite is supplied by Python's standard-library `sqlite3` module. The map requires an SQLite build with FTS5. Playwright is used only by the separate optional browser checks, not by the archive runtime.
