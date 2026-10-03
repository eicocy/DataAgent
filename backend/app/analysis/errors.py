class ToolError(ValueError):
    def __init__(self, code, message='工具输入或结果未通过验证', details=None, recoverable=False, suggestion='检查字段、类型与参数'):
        super().__init__(code)
        self.code, self.public_message = code, message
        self.details, self.recoverable, self.suggestion = details or {}, recoverable, suggestion

    def structured(self):
        return dict(code=self.code, message=self.public_message, details=self.details, recoverable=self.recoverable, suggestion=self.suggestion)


class ToolInputError(ToolError):
    """Invalid parameters."""


class ToolExecutionError(ToolError):
    """Calculation failure."""


class ToolResultError(ToolError):
    """Invalid calculated output."""


class DatasetColumnError(ToolInputError):
    """Unknown column."""


class DatasetTypeError(ToolInputError):
    """Incompatible dtype."""


class StatisticsError(ToolExecutionError):
    """Undefined or invalid statistics."""
