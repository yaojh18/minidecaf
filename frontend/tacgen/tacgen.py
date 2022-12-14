import utils.riscv as riscv
from frontend.ast import node
from frontend.ast.tree import *
from frontend.ast.visitor import Visitor
from frontend.symbol.varsymbol import VarSymbol
from frontend.type.array import ArrayType
from utils.tac import tacop
from utils.tac.funcvisitor import FuncVisitor
from utils.tac.programwriter import ProgramWriter
from utils.tac.tacprog import TACProg
from utils.tac.temp import Temp

"""
The TAC generation phase: translate the abstract syntax tree into three-address code.
"""


class TACGen(Visitor[FuncVisitor, None]):
    def __init__(self) -> None:
        pass

    # Entry of this phase
    def transform(self, program: Program) -> TACProg:
        mainFunc = program.mainFunc()
        pw = ProgramWriter(["main"])
        # The function visitor of 'main' is special.
        mv = pw.visitMainFunc()

        mainFunc.body.accept(self, mv)
        # Remember to call mv.visitEnd after the translation a function.
        mv.visitEnd()

        # Remember to call pw.visitEnd before finishing the translation phase.
        return pw.visitEnd()

    def visitBlock(self, block: Block, mv: FuncVisitor) -> None:
        for child in block:
            child.accept(self, mv)

    def visitReturn(self, stmt: Return, mv: FuncVisitor) -> None:
        stmt.expr.accept(self, mv)
        mv.visitReturn(stmt.expr.getattr("val"))

    def visitBreak(self, stmt: Break, mv: FuncVisitor) -> None:
        mv.visitBranch(mv.getBreakLabel())

    def visitContinue(self, stmt: Continue, mv: FuncVisitor) -> None:
        mv.visitBranch(mv.getContinueLabel())

    def visitIdentifier(self, ident: Identifier, mv: FuncVisitor) -> None:
        """
        1. Set the 'val' attribute of ident as the temp variable of the 'symbol' attribute of ident.
        """
        symbol = ident.getattr("symbol")
        ident.setattr("val", symbol.temp)

    def visitDeclaration(self, decl: Declaration, mv: FuncVisitor) -> None:
        """
        1. Get the 'symbol' attribute of decl.
        2. Use mv.freshTemp to get a new temp variable for this symbol.
        3. If the declaration has an initial value, use mv.visitAssignment to set it.
        """
        symbol = decl.getattr("symbol")
        symbol.temp = mv.freshTemp()
        if not isinstance(decl.init_expr, node.NullType):
            decl.init_expr.accept(self, mv)
            mv.visitAssignment(symbol.temp, decl.init_expr.getattr("val"))

    def visitAssignment(self, expr: Assignment, mv: FuncVisitor) -> None:
        """
        1. Visit the right hand side of expr, and get the temp variable of left hand side.
        2. Use mv.visitAssignment to emit an assignment instruction.
        3. Set the 'val' attribute of expr as the value of assignment instruction.
        """
        expr.rhs.accept(self, mv)
        symbol = expr.lhs.getattr("symbol")
        expr.setattr("val", mv.visitAssignment(symbol.temp, expr.rhs.getattr("val")))

    def visitIf(self, stmt: If, mv: FuncVisitor) -> None:
        stmt.cond.accept(self, mv)

        if stmt.otherwise is NULL:
            skipLabel = mv.freshLabel()
            mv.visitCondBranch(
                tacop.CondBranchOp.BEQ, stmt.cond.getattr("val"), skipLabel
            )
            stmt.then.accept(self, mv)
            mv.visitLabel(skipLabel)
        else:
            skipLabel = mv.freshLabel()
            exitLabel = mv.freshLabel()
            mv.visitCondBranch(
                tacop.CondBranchOp.BEQ, stmt.cond.getattr("val"), skipLabel
            )
            stmt.then.accept(self, mv)
            mv.visitBranch(exitLabel)
            mv.visitLabel(skipLabel)
            stmt.otherwise.accept(self, mv)
            mv.visitLabel(exitLabel)

    def visitFor(self, stmt: For, mv: FuncVisitor) -> None:
        beginLabel = mv.freshLabel()
        loopLabel = mv.freshLabel()
        breakLabel = mv.freshLabel()
        stmt.init.accept(self, mv)

        mv.openLoop(breakLabel, loopLabel)
        mv.visitLabel(beginLabel)
        if not isinstance(stmt.cond, node.NullType):
            stmt.cond.accept(self, mv)
            mv.visitCondBranch(tacop.CondBranchOp.BEQ, stmt.cond.getattr("val"), breakLabel)
        stmt.body.accept(self, mv)
        mv.visitLabel(loopLabel)
        stmt.update.accept(self, mv)
        mv.visitBranch(beginLabel)
        mv.visitLabel(breakLabel)

        mv.closeLoop()



    def visitWhile(self, stmt: While, mv: FuncVisitor) -> None:
        beginLabel = mv.freshLabel()
        loopLabel = mv.freshLabel()
        breakLabel = mv.freshLabel()
        mv.openLoop(breakLabel, loopLabel)

        mv.visitLabel(beginLabel)
        stmt.cond.accept(self, mv)
        mv.visitCondBranch(tacop.CondBranchOp.BEQ, stmt.cond.getattr("val"), breakLabel)

        stmt.body.accept(self, mv)
        mv.visitLabel(loopLabel)
        mv.visitBranch(beginLabel)
        mv.visitLabel(breakLabel)
        mv.closeLoop()

    def visitDoWhile(self, stmt: DoWhile, mv: FuncVisitor) -> None:
        loopLabel = mv.freshLabel()
        breakLabel = mv.freshLabel()
        mv.openLoop(breakLabel, loopLabel)

        mv.visitLabel(loopLabel)
        stmt.body.accept(self, mv)
        stmt.cond.accept(self, mv)
        mv.visitCondBranch(tacop.CondBranchOp.BNE, stmt.cond.getattr("val"), loopLabel)
        mv.visitLabel(breakLabel)
        mv.closeLoop()

    def visitUnary(self, expr: Unary, mv: FuncVisitor) -> None:
        expr.operand.accept(self, mv)

        op = {
            node.UnaryOp.Neg: tacop.UnaryOp.NEG,
            node.UnaryOp.BitNot: tacop.UnaryOp.NOT,
            node.UnaryOp.LogicNot: tacop.UnaryOp.SEQZ
        }[expr.op]
        expr.setattr("val", mv.visitUnary(op, expr.operand.getattr("val")))

    def visitBinary(self, expr: Binary, mv: FuncVisitor) -> None:
        expr.lhs.accept(self, mv)
        expr.rhs.accept(self, mv)

        if expr.op == node.BinaryOp.LogicOr:
            newReg = mv.visitBinary(tacop.BinaryOp.OR, expr.lhs.getattr("val"), expr.rhs.getattr("val"))
            mv.visitUnarySelf(tacop.UnaryOp.SNEZ, newReg)
            expr.setattr("val", newReg)
        elif expr.op == node.BinaryOp.LogicAnd:
            newReg1 = mv.visitUnary(tacop.UnaryOp.SNEZ, expr.lhs.getattr("val"))
            newReg2 = mv.visitUnary(tacop.UnaryOp.SNEZ, expr.rhs.getattr("val"))
            mv.visitBinarySelf(tacop.BinaryOp.AND, newReg1, newReg2)
            expr.setattr("val", newReg1)
        elif expr.op == node.BinaryOp.LE:
            newReg = mv.visitBinary(tacop.BinaryOp.SGT, expr.lhs.getattr("val"), expr.rhs.getattr("val"))
            mv.visitUnarySelf(tacop.UnaryOp.SEQZ, newReg)
            expr.setattr("val", newReg)
        elif expr.op == node.BinaryOp.GE:
            newReg = mv.visitBinary(tacop.BinaryOp.SLT, expr.lhs.getattr("val"), expr.rhs.getattr("val"))
            mv.visitUnarySelf(tacop.UnaryOp.SEQZ, newReg)
            expr.setattr("val", newReg)
        elif expr.op == node.BinaryOp.EQ:
            newReg = mv.visitBinary(tacop.BinaryOp.SUB, expr.lhs.getattr("val"), expr.rhs.getattr("val"))
            mv.visitUnarySelf(tacop.UnaryOp.SEQZ, newReg)
            expr.setattr("val", newReg)
        elif expr.op == node.BinaryOp.NE:
            newReg = mv.visitBinary(tacop.BinaryOp.SUB, expr.lhs.getattr("val"), expr.rhs.getattr("val"))
            mv.visitUnarySelf(tacop.UnaryOp.SNEZ, newReg)
            expr.setattr("val", newReg)
        else:
            op = {
                node.BinaryOp.Add: tacop.BinaryOp.ADD,
                node.BinaryOp.Sub: tacop.BinaryOp.SUB,
                node.BinaryOp.Mul: tacop.BinaryOp.MUL,
                node.BinaryOp.Div: tacop.BinaryOp.DIV,
                node.BinaryOp.Mod: tacop.BinaryOp.REM,
                node.BinaryOp.LT: tacop.BinaryOp.SLT,
                node.BinaryOp.GT: tacop.BinaryOp.SGT
            }[expr.op]
            expr.setattr(
                "val", mv.visitBinary(op, expr.lhs.getattr("val"), expr.rhs.getattr("val"))
            )

    def visitCondExpr(self, expr: ConditionExpression, mv: FuncVisitor) -> None:
        """
        1. Refer to the implementation of visitIf and visitBinary.
        """
        expr.cond.accept(self, mv)
        skipLabel = mv.freshLabel()
        returnValue = mv.freshTemp()
        expr.otherwise.accept(self, mv)
        mv.visitAssignment(returnValue,expr.otherwise.getattr("val"))
        mv.visitCondBranch(
            tacop.CondBranchOp.BEQ, expr.cond.getattr("val"), skipLabel
        )
        expr.then.accept(self, mv)
        mv.visitAssignment(returnValue, expr.then.getattr("val"))
        mv.visitLabel(skipLabel)
        expr.setattr("val", returnValue)

    def visitIntLiteral(self, expr: IntLiteral, mv: FuncVisitor) -> None:
        expr.setattr("val", mv.visitLoad(expr.value))
