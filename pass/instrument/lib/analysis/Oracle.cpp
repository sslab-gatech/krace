#include "analysis/Oracle.h"

namespace racer {

    // dominator
    BasicBlock *FuncOracle::getIDom(BasicBlock *bb) {
        DomTreeNodeBase<BasicBlock> *node = dt.getNode(bb);
        assert(node != nullptr);

        DomTreeNodeBase<BasicBlock> *idom = node->getIDom();
        if (idom == nullptr) {
            return nullptr;
        }

        return idom->getBlock();
    }

    // loop
    Loop *FuncOracle::getOuterLoopInScope(Loop *scope, BasicBlock *bb) {
        Loop *l = li.getLoopFor(bb);
        Loop *c = nullptr;

        while (l != scope) {
            c = l;
            l = l->getParentLoop();
        }

        return c;
    }

} /* namespace racer */
