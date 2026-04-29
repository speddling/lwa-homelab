# Commands

## CLI Arguments

K9s CLI comes with a view arguments that you can use to launch the tool with different configuration.

```
# List all available CLI options
k9s help
# Get info about K9s runtime (logs, configs, etc..)
k9s info
# Run K9s in a given namespace.
k9s -n mycoolns
# Run K9s and launch in pod view via the pod command.
k9s -c pod
# Start K9s in a non default KubeConfig context
k9s --context coolCtx
# Start K9s in readonly mode - with all modification commands disabled
k9s --readonly
```

## Key Bindings

| Action | Command | Comment |
| --- | --- | --- |
| Show active keyboard mnemonics and help | `?` |  |
| Show all available resource alias | `ctrl-a` |  |
| To bail out of K9s | `:q`, `ctrl-c` |  |
| View a Kubernetes resource using singular/plural or short-name | `:`pod⏎ | accepts singular, plural, short-name or alias ie pod or pods |
| View a Kubernetes resource in a given namespace | `:`pod ns-x⏎ |  |
| View filtered pods | `:`pod /fred⏎ | View all pods filtered by fred |
| View labeled pods | `:`pod app=fred,env=dev⏎ | View all pods with labels matching app=fred and env=dev |
| View pods in a given context | `:`pod @ctx1⏎ | View all pods in context ctx1. Switches out your current k9s context! |
| Filter out a resource view given a filter | `/`filter⏎ | Regex2 supported ie `fred|blee` to filter resources named fred or blee |
| Inverse regex filter | `/`! filter⏎ | Keep everything that _doesn’t_ match. |
| Filter resource view by labels | `/`-l label-selector⏎ |  |
| Fuzzy find a resource given a filter | `/`-f filter⏎ |  |
| Bails out of view/command/filter mode | `<esc>` |  |
| Key mapping to describe, view, edit, view logs,… | `d`,`v`, `e`, `l`,… |  |
| To view and switch to another Kubernetes context (Pod view) | `:`ctx⏎ |  |
| To view and switch directly to another Kubernetes context (Last used view) | `:`ctx context-name⏎ |  |
| To view and switch to another Kubernetes namespace | `:`ns⏎ |  |
| To view all saved resources | `:`screendump or sd⏎ |  |
| To delete a resource (TAB and ENTER to confirm) | `ctrl-d` |  |
| To kill a resource (no confirmation dialog, equivalent to kubectl delete –now) | `ctrl-k` |  |
| Launch pulses view | `:`pulses or pu⏎ |  |
| Launch XRay view | `:`xray RESOURCE \[NAMESPACE\]⏎ | RESOURCE can be one of po, svc, dp, rs, sts, ds, NAMESPACE is optional |
