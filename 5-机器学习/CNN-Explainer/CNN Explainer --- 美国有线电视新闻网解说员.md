> 打开链接体验卷积神经解释器（CNN Explainer）：https://poloclub.github.io/cnn-explainer

视频演示：

<iframe id="demo_video" frameborder="0" allowfullscreen="1" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" title="Demo Video &quot;CNN Explainer: Learning Convolutional Neural Networks with Interactive Visualization&quot;" width="640" height="360" src="https://www.bilibili.com/video/BV1Rr4y1Z7Xh/"></iframe>



![CNN Explainer 网站界面](https://image-1315363329.cos.ap-shanghai.myqcloud.com/lessons/202309211536545.png)

上图 `TinyVGG` 卷积神经网络模型可以简化为：

![`TinyVGG` 卷积神经网络模型简化图](https://image-1315363329.cos.ap-shanghai.myqcloud.com/lessons/202309211848660.png)

用 `PytTorch` 代码表示此模型结构（看懂结构就行）：

```python
class CNNModel(nn.Module):
    """
    Model architecture copying TinyVGG from: 
    https://poloclub.github.io/cnn-explainer/
    """
    def __init__(self, input_shape: int, hidden_units: int, output_shape: int):
        super().__init__()
        self.block_1 = nn.Sequential(
            # nn.Conv2d() ，也称为卷积层。
            nn.Conv2d(in_channels=input_shape,  
                      out_channels=hidden_units, 
                      kernel_size=3, # 图像上的卷积核的大小，此处为3*3
                      stride=1, # default
                      padding=1), # 填充层
            nn.ReLU(), # 激活函数
            nn.Conv2d(in_channels=hidden_units, 
                      out_channels=hidden_units,
                      kernel_size=3,
                      stride=1,
                      padding=1),
            nn.ReLU(),
            # nn.MaxPool2d() ，也称为最大池化层。
            nn.MaxPool2d(kernel_size=2,
                         stride=2) # 默认的步长和kernel_size大小相等
        )
        self.block_2 = nn.Sequential(
            nn.Conv2d(hidden_units, hidden_units, 3, padding=1),
            nn.ReLU(),
            nn.Conv2d(hidden_units, hidden_units, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2)
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(in_features=hidden_units*7*7, 
                      out_features=output_shape)
        )
    
    def forward(self, x: torch.Tensor):
        x = self.block_1(x)
        # print(x.shape)
        x = self.block_2(x)
        # print(x.shape)
        x = self.classifier(x)
        # print(x.shape)
        return x
```



## 什么是卷积神经网络？

在机器学习中，分类器为数据点分配种类标签。例如，图像分类器为图像中存在的对象生成类标签（例如，鸟、飞机）。卷积神经网络（简称CNN）是一种分类器，它擅长解决这个问题！

CNN 是一种神经网络：一种用于识别数据模式的算法。神经网络通常由分层组织的神经元集合组成，每个神经元都有自己的可学习权重和偏差。让我们将 CNN 分解为其基本构建块。

1.  **张量 *tensor*** 可以被认为是一个 n 维矩阵。在上面的 CNN 中，除了输出层之外，张量都是 3 维的。
2.  **神经元 *neuron* **可以被认为是一个接受多个输入并产生单个输出的函数。神经元的输出在上面表示为红色→蓝色激活图。
3.  **层 *layer*** 只是具有相同操作（包括相同超参数*hyperparameters*）的神经元的集合。
4.  **内核Kernel** **权重*weights*** 和 **偏差*biases***，虽然对于每个神经元来说都是唯一的，但在训练阶段进行调整，并允许分类器适应所提供的问题和数据集。它们在可视化中使用黄色→绿色发散的色阶进行编码。通过单击神经元或将鼠标悬停在卷积弹性解释视图中的内核/偏差上，可以在交互式公式视图中查看具体值。
5.  CNN 传递可微分数函数 *differentiable score function* ，该函数在输出层的可视化中表示为各类别得分。

如果您以前研究过神经网络，这些术语可能听起来很熟悉。那么是什么让 CNN 与众不同呢？ CNN 使用一种特殊类型的层（恰当地称为卷积层），这使得它们能够很好地从图像和类图像数据中学习。对于图像数据，CNN 可用于许多不同的计算机视觉任务，例如[图像处理、分类、分割和对象检测](http://ijcsit.com/docs/Volume%207/vol7issue5/ijcsit20160705014.pdf)。

在 **CNN 解释器** 中，您可以了解如何使用简单的 CNN 进行图像分类。由于网络的简单性，其性能并不完美，但没关系！ **CNN 解释器** 中使用的网络架构 [Tiny VGG](http://cs231n.stanford.edu/) 包含许多与当今最先进的 CNN 中使用的相同的层和操作，但规模较小。这样入门起来会更容易理解。

## 网络的每一层都有什么作用？

让我们点击浏览一下网络中的每一层。在阅读时，请通过单击并将鼠标悬停在上面的可视化的各个部分上，随意与上面的可视化进行交互。

#### 输入层 Input Layer

输入层（最左边的层）代表 CNN 的输入图像。因为我们使用 RGB 图像作为输入，所以输入层具有三个通道，分别对应于该层中显示的红色、绿色和蓝色通道。单击上面的 **details** 图标时使用色阶来显示详细信息（有关此图层和其他图层的信息)。

![显示细节](https://image-1315363329.cos.ap-shanghai.myqcloud.com/lessons/202309211536546.png)

#### 卷积层 Convolutional Layers 

![卷积层示意](https://image-1315363329.cos.ap-shanghai.myqcloud.com/lessons/202309211849263.png)

卷积层是 CNN 的基础，因为它们包含学习的内核（权重），可以提取区分不同图像的特征——这就是我们想要进行分类的！当您与卷积层交互时，您会注意到前面的层和卷积层之间的链接。每个链接代表一个独特的内核，用于卷积运算以产生当前卷积神经元的输出或激活图。

卷积神经元使用唯一的内核和前一层相应神经元的输出执行[元素点积](https://baike.baidu.com/item/%E7%82%B9%E7%A7%AF/9648528)。这将产生与唯一内核一样多的中间结果。卷积神经元是所有中间结果与学习偏差相加的结果。

例如，让我们看一下上面 Tiny VGG 架构中的第一个卷积层。请注意，这一层有 10 个神经元，但上一层只有 3 个神经元。在 Tiny VGG 架构中，卷积层是全连接的，这意味着每个神经元都与前一层中的每个其他神经元连接。关注第一个卷积层最顶层卷积神经元的输出，当我们将鼠标悬停在激活图上时，我们看到有 3 个独特的内核。

![图 1 clicking on topmost first conv. layer activation map](https://image-1315363329.cos.ap-shanghai.myqcloud.com/lessons/202309211538642.gif)

图 1. 当您将鼠标悬停在第一个卷积层最顶层节点的激活图上时，您可以看到应用了 3 个内核来生成此激活图。单击此激活图后，您可以看到每个独特内核发生的卷积运算。

这些内核的大小是由网络架构设计者指定的超参数。为了产生卷积神经元的输出（激活图），我们必须与前一层的输出和网络学习的唯一内核执行元素点积。在 TinyVGG 中，点积运算使用步长 1，这意味着每个点积内核移动超过 1 个像素，但这是一个超参数，网络架构设计者可以调整该超参数以更好地适应其数据集。我们必须对所有 3 个内核执行此操作，这将产生 3 个中间结果。

<img src="https://image-1315363329.cos.ap-shanghai.myqcloud.com/lessons/202309211538643.gif" alt="图 2 clicking on topmost first conv. layer activation map" />

图 2. 应用内核来生成所讨论的激活图的最顶层中间结果。

然后，执行元素求和，其中包含所有 3 个中间结果以及网络学到的偏差。此后，生成的二维张量将是在上面的界面上可看到的第一个卷积层中最顶层神经元的激活图。必须应用相同的操作来生成每个神经元的激活图。

通过一些简单的数学计算，我们可以推断出有 3 x 10 = 30 个独特的内核，每个内核的大小为 3x3，应用于第一个卷积层。卷积层和前一层之间的连接是构建网络架构时的设计决策，这将影响每个卷积层的内核数量。单击可视化周围可以更好地了解卷积层背后的操作。看看你能不能按照上面的例子去做！

#### 了解超参数 Understanding Hyperparameters  
![超参数](https://image-1315363329.cos.ap-shanghai.myqcloud.com/lessons/202309211536547.gif)

![超参数-padding](https://image-1315363329.cos.ap-shanghai.myqcloud.com/lessons/202309211536548.gif)

1.  **填充** `Padding`：当内核超出激活图时，通常需要填充。填充可以保留激活图边界处的数据，从而获得更好的性能，并且可以帮助[保留输入的空间大小](https://arxiv.org/pdf/1603.07285.pdf)，从而允许架构设计人员构建更简洁、性能更高的网络。存在[多种填充技术](https://arxiv.org/pdf/1811.11718.pdf)，但最常用的方法是零填充，因为它的性能、简单性和计算效率较高。该技术涉及在输入边缘对称地添加零。这种方法被许多高性能 CNN 所采用，例如 [AlexNet](https://papers.nips.cc/paper/4824-imagenet-classification-with-deep-convolutional-neural-networks.pdf)。
2.  内核大小 `Kernel size`，通常也称为过滤器大小 `filter size`，是指输入上滑动窗口的尺寸。选择这个超参数对图像分类任务有很大的影响。例如，较小的内核尺寸能够从输入中提取包含高度局部特征的大量信息。正如您在上面的可视化中所看到的，较小的内核尺寸也会导致层尺寸的减小较小，从而允许更深的架构。相反，较大的内核提取的信息较少，这会导致层维度更快地减少，通常会导致性能较差。大内核更适合提取更大的特征。归根结底，选择合适的内核大小将取决于您的任务和数据集，但通常，较小的内核大小会带来更好的图像分类任务性能，因为架构设计者能够[将越来越多的层堆叠在一起学习越来越复杂的功能](https://arxiv.org/pdf/1409.1556.pdf)！
3.  **步幅** `Stride` 指示内核一次应移动多少像素。例如，如上面的卷积层示例中所述，Tiny VGG 在其卷积层中使用步长 1，这意味着在输入的 3x3 窗口上执行点积以产生输出值，然后移位到对于每个后续操作，右移一个像素。步幅对 CNN 的影响与内核大小类似。随着步幅减小，由于提取了更多数据，因此可以学习更多特征，这也导致输出层更大。相反，随着步幅的增加，这会导致特征提取更加有限和输出层尺寸更小。架构设计者的职责之一是确保内核在实现 CNN 时对称地滑过输入。使用上面的超参数可视化来改变各种输入/内核维度的步幅，以理解此约束！

#### 激活函数 Activation Functions 

##### ReLU

神经网络在现代技术中极为普遍——因为它们非常准确！当今性能最高的 CNN 包含[数量惊人的层](https://arxiv.org/pdf/1512.03385.pdf)，这些层能够学习越来越多的特征。这些突破性的 CNN 能够达到如此高的精度的部分原因是它们的非线性。 ReLU 将急需的非线性应用到模型中。非线性对于产生非线性决策边界是必要的，因此输出不能写成输入的线性组合。如果不存在非线性激活函数，深度 CNN 架构将退化为单个等效卷积层，其性能几乎不会那么好。 ReLU 激活函数专门用作非线性激活函数，与 Sigmoid 等其他非线性函数相反，因为根据[经验观察](https://arxiv.org/pdf/1906.01975.pdf)，使用 ReLU 的 CNN 训练速度比其对应函数更快。

ReLU激活函数是一对一的数学运算：

<img src="https://image-1315363329.cos.ap-shanghai.myqcloud.com/lessons/202309211538644.png" alt="relu graph" style="zoom:50%;" />

图 3.绘制的 ReLU 激活函数，它忽略所有负数据。

![ReLU激活函数](https://image-1315363329.cos.ap-shanghai.myqcloud.com/lessons/202309211536550.gif)

该激活函数按元素应用于输入张量中的每个值。例如，如果对值 2.24 应用 ReLU，结果将为 2.24，因为 2.24 大于 0。您可以通过单击上面网络中的 ReLU 神经元来观察如何应用此激活函数。修正线性激活函数 (ReLU) 在上述网络架构中的每个卷积层之后执行。请注意该层对整个网络中各种神经元激活图的影响！

##### Softmax


$$
\text{Softmax}(x_{i}) = \frac{\exp(x_i)}{\sum_j \exp(x_j)}
$$

softmax 运算有一个关键目的：因为预测类别的概率总和为1，所以softmax 确保 CNN 输出总和为 1。因此，softmax 运算对于将模型输出缩放为概率非常有用。单击最后一层可显示网络中的 softmax 操作。请注意展平后的 logits 不会在 0 到 1 之间缩放。为了直观地指示每个 logit（未缩放标量值）的影响，它们使用浅橙色 → 深橙色色标进行编码。经过softmax函数后，现在每个类都对应了一个适当的概率！

您可能会想标准归一化和 softmax 之间的区别是什么 - 毕竟，两者都在 0 和 1 之间重新调整 logits。请记住，反向传播是训练神经网络的一个关键方面 - 我们希望正确的答案具有最大的“信号”。 ”通过使用 softmax，我们可以有效地“逼近”argmax，同时获得可微性。重新缩放不会使最大值的权重显着高于其他 logits，而 softmax 却会。简而言之，softmax 是一个“更软”的 argmax——看看我们在那里做了什么？

![softmax interactive formula view](https://image-1315363329.cos.ap-shanghai.myqcloud.com/lessons/202309211538645.gif)

图 4.Softmax 交互式公式视图允许用户与颜色编码的 logits 和公式进行交互，以了解展平层后的预测分数如何标准化以产生分类分数。

#### 池化层 Pooling Layers 

不同的CNN架构中有多种类型的池化层，但它们的目的都是逐渐减小网络的空间范围，从而减少网络的参数和整体计算量。上面的 Tiny VGG 架构中使用的池化类型是 Max-Pooling。
最大池化操作需要在架构设计期间选择内核大小和步长。一旦选择，该操作就会以指定的步幅在输入上滑动内核，同时仅从输入中选择每个内核切片的最大值以产生输出值。这个过程可以通过点击上面网络中的池化神经元来查看。

![池化层](https://image-1315363329.cos.ap-shanghai.myqcloud.com/lessons/202309211903454.png)



#### 展平层 Flatten Layer 

该层将网络中的三维层转换为一维向量，以拟合全连接层的输入进行分类。例如，5x5x2 张量将转换为大小为 50 的向量。网络的先前卷积层从输入图像中提取特征，但现在是时候对特征进行分类了。我们使用softmax函数对这些特征进行分类，这需要一维输入。这就是为什么需要平坦层的原因。可以通过单击任何输出类来查看该层。CNN 解释器是如何实现的？

CNN Expander 使用 [TensorFlow.js](https://js.tensorflow.org/)（一个浏览器内 GPU 加速的深度学习库）来加载预训练模型以进行可视化。整个交互系统是用 Javascript 编写的，使用 [Svelte](https://svelte.dev/) 作为框架，使用 [D3.js](https://d3js.org/) 进行可视化。您现在只需要一个网络浏览器就可以开始学习 CNN！

## 谁开发了 CNN 解释器？

CNN Explaner 由  [Jay Wang](https://zijie.wang/), [Robert Turko](https://www.linkedin.com/in/robert-turko/), [Omar Shaikh](http://oshaikh.com/), [Haekyu Park](https://haekyu.com/), [Nilaksh Das](http://nilakshdas.com/), [Fred Hohman](https://fredhohman.com/), [Minsuk Kahng](http://minsuk.com/), 和[Polo Chau](https://www.cc.gatech.edu/~dchau/) 创建，是佐治亚理工学院与俄勒冈州立大学合作研究的成果。我们感谢 Anmol Chhabria、Kaan Sancak、Kantwon Rogers 和佐治亚理工学院可视化实验室的支持和建设性反馈。这项工作得到了 NSF 赠款 IIS-1563816、CNS-1704701、NASA NSTRF、DARPA GARD 以及来自 Intel、NVIDIA、Google、Amazon 的捐赠的部分支持。