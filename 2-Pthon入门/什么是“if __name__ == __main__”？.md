

## 什么是 `if __name__ == "__main__"`？

当你开始了解 Python 时，初学者经常会遇到看似神秘的一行： `if __name__ == "__main__":` 。在python文件（即脚本）中似乎加不加这一行，对代码运行都没有什么影响，这引起了我的疑问，在查阅了一些资料才理解：

 `if __name__ == "__main__" `，这种特定的代码模式充当保护措施，防止脚本被其他文件导入时，意外执行此行 `if __name__ == "__main__" `之后的代码。当这种保护机制缺失时，

### Python 中的模块与脚本

在 Python 中，每个带有 `.py` 扩展名的文件本质上都是一个模块。该模块可以定义函数、类和变量。它还可以包含可运行的代码。模块可以在其他 Python 文件或模块中导入和使用。这种模块化方法促进了代码的重用和可维护性。

每个 Python 模块都有一个名为 `__name__` 的内置属性。当您直接运行 Python 文件时， `__name__` 属性将设置为 `"__main__"` 。但是，如果您在另一个脚本中导入此文件/模块，则 `__name__` 属性将设置为文件/模块的名称。

例如，创建一个名为 `test.py` 的文件，其中包含以下内容：

```python
print("This is example.py")
print("__name__ is:", __name__)
```

当您运行此 `test.py` 时，您将获得以下输出：

```python
This is example.py
__name__ is: __main__
```

但是，如果我们有另一个脚本 `main_script.py` ，它导入 `test.py` ：

```python
import test
print("This is main_script.py")
```

当您运行 `main_script.py` 时，输出将变为：

```python
$ python3 main_script.py
This is example.py
__name__ is: test
This is main_script.py
```



现在我们了解了 `__name__` 属性，让我们看看构造本身。

如果您希望某些代码仅在执行脚本时（而不是在导入脚本时）运行，则可以将该代码放在 `if __name__ == "__main__":` 块下。
使用上面的示例，让我们修改 `test.py` ：

```python
def main_function():
    print("Main function in example.py")

if __name__ == "__main__":
    main_function()
```

现在，如果直接运行 `test.py` ， `main_function()` 将被执行。但是，如果您在另一个脚本中导入 `test.py` ，则不会自动调用 `main_function()` ，以确保导入脚本可以控制执行流程。
