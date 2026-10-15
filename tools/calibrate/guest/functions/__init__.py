"""SeBS-equivalent function kernels run inside the guest (doc 10 §3 ``sebs``). Each module defines
``make_input(size_kb)`` and ``handler(inp)`` and mirrors the computation of the SeBS benchmark of the same name
(Copik et al., Middleware'21) without its cloud storage: inputs are generated in the guest."""
