import torch
from tensordict import TensorDict
from tensordict.nn import make_functional, TensorDictModuleBase
from torch import nn


class EnsembleModule(TensorDictModuleBase):
    """Module that wraps a module and repeats it to form an ensemble.

    Args:
        module (nn.Module): The nn.module to duplicate and wrap.
        num_copies (int): The number of copies of module to make.
        parameter_init_function (Callable): A function that takes a module copy and initializes its parameters.
        expand_input (bool): Whether to expand the input TensorDict to match the number of copies. This should be
            True unless you are chaining ensemble modules together, e.g. EnsembleModule(cnn) -> EnsembleModule(mlp).
            If False, EnsembleModule(mlp) will expected the previous module(s) to have already expanded the input.

    Examples:
        >>> import torch
        >>> from torch import nn
        >>> from tensordict.nn import TensorDictModule
        >>> from torchrl.modules import EnsembleModule
        >>> from tensordict import TensorDict
        >>> net = nn.Sequential(nn.Linear(4, 32), nn.ReLU(), nn.Linear(32, 2))
        >>> mod = TensorDictModule(net, in_keys=['a'], out_keys=['b'])
        >>> ensemble = EnsembleModule(mod, num_copies=3)
        >>> data = TensorDict({'a': torch.randn(10, 4)}, batch_size=[10])
        >>> ensemble(data)
        TensorDict(
            fields={
                a: Tensor(shape=torch.Size([3, 10, 4]), device=cpu, dtype=torch.float32, is_shared=False),
                b: Tensor(shape=torch.Size([3, 10, 2]), device=cpu, dtype=torch.float32, is_shared=False)},
            batch_size=torch.Size([3, 10]),
            device=None,
            is_shared=False)

        >>> import torch
        >>> from tensordict.nn import TensorDictModule, TensorDictSequential
        >>> from torchrl.modules import EnsembleModule
        >>> from tensordict import TensorDict
        >>> module = TensorDictModule(torch.nn.Linear(2,3), in_keys=['bork'], out_keys=['dork'])
        >>> next_module = TensorDictModule(torch.nn.Linear(3,1), in_keys=['dork'], out_keys=['spork'])
        >>> e0 = EnsembleModule(module, num_copies=4, expand_input=True)
        >>> e1 = EnsembleModule(next_module, num_copies=4, expand_input=False)
        >>> seq = TensorDictSequential(e0, e1)
        >>> data = TensorDict({'bork': torch.randn(5,2)}, batch_size=[5])
        >>> seq(data)
        TensorDict(
            fields={
                bork: Tensor(shape=torch.Size([4, 5, 2]), device=cpu, dtype=torch.float32, is_shared=False),
                dork: Tensor(shape=torch.Size([4, 5, 3]), device=cpu, dtype=torch.float32, is_shared=False),
                spork: Tensor(shape=torch.Size([4, 5, 1]), device=cpu, dtype=torch.float32, is_shared=False)},
            batch_size=torch.Size([4, 5]),
            device=None,
            is_shared=False)
    """

    def __init__(
        self,
        module: TensorDictModuleBase,
        num_copies: int,
        expand_input: bool = True,
    ):
        super().__init__()
        self.in_keys = module.in_keys
        self.out_keys = module.out_keys
        params_td = make_functional(module).expand(num_copies).to_tensordict()
        module.reset_parameters(params_td)

        self.module = module
        self.params_td = params_td
        self.params = nn.ParameterList(list(self.params_td.values(True, True)))
        if expand_input:
            self.vmapped_forward = torch.vmap(self.module, (None, 0))
        else:
            self.vmapped_forward = torch.vmap(self.module, 0)

    def forward(self, tensordict: TensorDict) -> TensorDict:
        return self.vmapped_forward(tensordict, self.params_td)
