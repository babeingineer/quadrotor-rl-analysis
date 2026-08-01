"""Asymmetric actor-critic policy: the CRITIC sees the episode's hidden draw (aero
coefficients, mass, motor lag, fin gain/offset, true wind, yaw bias) appended to the
observation; the ACTOR sees only the deployable first ACTOR_DIM dims. Value targets become
predictable across DR draws, reducing advantage noise. The deployment artifact is unchanged
(actor input = policy obs).
"""
import torch as th
from torch import nn
from stable_baselines3.common.policies import ActorCriticPolicy


def _mlp(in_dim, arch, act):
    layers, d = [], in_dim
    for h in arch:
        layers += [nn.Linear(d, h), act()]
        d = h
    return nn.Sequential(*layers), d


class PrivExtractor(nn.Module):
    """Drop-in for SB3's MlpExtractor: policy branch reads only the first actor_dim
    features; value branch reads everything (obs + privileged tail)."""
    def __init__(self, feature_dim, actor_dim, net_arch, activation_fn):
        super().__init__()
        self.actor_dim = int(actor_dim)
        self.policy_net, self.latent_dim_pi = _mlp(self.actor_dim, net_arch, activation_fn)
        self.value_net, self.latent_dim_vf = _mlp(feature_dim, net_arch, activation_fn)

    def forward(self, features):
        return self.forward_actor(features), self.forward_critic(features)

    def forward_actor(self, features):
        return self.policy_net(features[..., : self.actor_dim])

    def forward_critic(self, features):
        return self.value_net(features)


class PrivACPolicy(ActorCriticPolicy):
    """ActorCriticPolicy with the sliced extractor. Pass actor_dim via policy_kwargs."""
    def __init__(self, *args, actor_dim=40, **kwargs):
        self._actor_dim = int(actor_dim)
        super().__init__(*args, **kwargs)

    def _build_mlp_extractor(self):
        arch = self.net_arch if isinstance(self.net_arch, list) else [256, 256]
        if isinstance(arch, dict):
            arch = arch.get("pi", [256, 256])
        self.mlp_extractor = PrivExtractor(self.features_dim, self._actor_dim,
                                           arch, self.activation_fn)
