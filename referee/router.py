"""Fast fastest-path routing on the SUMO network (free-flow travel time), one tree per origin and per destination."""
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

class Router:
    def __init__(self, net):
        self.edges = [e for e in net.getEdges() if e.allows('passenger') and not e.isSpecial()]
        self.idx = {e.getID(): i for i, e in enumerate(self.edges)}
        self.tt = np.array([e.getLength() / e.getSpeed() for e in self.edges])
        r, c, w = [], [], []
        for i, e in enumerate(self.edges):
            for f, conns in e.getOutgoing().items():
                j = self.idx.get(f.getID())
                if j is not None and any(cn.allows('passenger') if hasattr(cn, 'allows') else True for cn in conns):
                    r.append(i); c.append(j); w.append(self.tt[j] + 1e-3)
        n = len(self.edges)
        self.G = csr_matrix((w, (r, c)), shape=(n, n))
        self.ids = [e.getID() for e in self.edges]
    def tree_from(self, a):
        d, p = dijkstra(self.G, indices=self.idx[a], return_predecessors=True)
        return d, p
    def tree_to(self, b):
        d, p = dijkstra(self.G.T.tocsr(), indices=self.idx[b], return_predecessors=True)
        return d, p
    def path_from(self, a, tree, x):
        d, p = tree; j = self.idx[x]
        if not np.isfinite(d[j]): return None
        out = [j]
        while out[-1] != self.idx[a]: out.append(p[out[-1]])
        return [self.ids[k] for k in reversed(out)]
    def path_to(self, b, tree, x):
        d, p = tree; j = self.idx[x]
        if not np.isfinite(d[j]): return None
        out = [j]
        while out[-1] != self.idx[b]: out.append(p[out[-1]])
        return [self.ids[k] for k in out]
