# -*- coding: utf-8 -*-
"""DDPG_Agent.py

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1jyl0-RkR7CHU1PuEn9CUR7_y8GW7LqqL
"""

# Commented out IPython magic to ensure Python compatibility.
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
# %matplotlib inline

import os
import torch
import torch.nn as nn
from torch.utils.data import Dataset,DataLoader
import torch.optim as optim

import yfinance as yf
from collections import deque
import random
import math
from tqdm import tqdm

#DDPG Model

import torch
import torch.nn as nn
import torch.optim as optim
import random
from collections import deque

# DDPG Model
class ActorNetwork(nn.Module):
    def __init__(self, state_dim, action_dim):
        super(ActorNetwork, self).__init__()
        self.fc1 = nn.Linear(state_dim, 64)
        self.fc2 = nn.Linear(64, 32)
        self.fc3 = nn.Linear(32, 8)
        self.fc4 = nn.Linear(8, action_dim)

    def forward(self, x):
        x = torch.relu(self.fc1(x))
        x = torch.relu(self.fc2(x))
        x = torch.relu(self.fc3(x))
        output = torch.tanh(self.fc4(x))
        return output

class CriticNetwork(nn.Module):
    def __init__(self, state_dim, action_dim):
        super(CriticNetwork, self).__init__()
        self.fc1 = nn.Linear(state_dim + action_dim, 64)
        self.fc2 = nn.Linear(64, 32)
        self.fc3 = nn.Linear(32, 8)
        self.fc4 = nn.Linear(8, 1)

    def forward(self, x):
        x = torch.relu(self.fc1(x))
        x = torch.relu(self.fc2(x))
        x = torch.relu(self.fc3(x))
        output = self.fc4(x)
        return output

class OrnsteinUhlenbeckNoise:
    "OU noise generator class, used to add OU noise to actions."
    def __init__(self, size, mu=0, sigma=0.1, theta=0.15):
        self.mu = mu * np.ones(size)
        self.sigma = sigma
        self.theta = theta
        self.size = size
        self.reset()

    def reset(self):
        "Resets noise to mean."
        self.state = self.mu.copy()

    def sample(self):
        "Returns next value generated in process."
        dx = self.theta * (self.mu - self.state) + self.sigma * np.random.randn(self.size)
        self.state += dx
        return self.state.copy()

# DPMG Agent
class DDPG_Agent:
    def __init__(self, state_dim, tau=0.0001, is_eval=False, model_name=""):
        self.model_type = "DDPG"
        self.state_dim = state_dim
        self.action_dim = 3  # hold, sell, and buy
        self.memory = deque(maxlen=100)
        self.buffer_size = 60

        self.gamma = 0.95
        self.is_eval = is_eval
        self.tau = tau
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.noise_generator = OrnsteinUhlenbeckNoise(size=self.action_dim, mu=0)

        # if is_eval:
        #     self.model = self.create_model().to(self.device)
        #     self.model_target = self.create_model().to(self.device)

        #     if self.device.type == 'cpu':
        #         self.model.load_state_dict(torch.load(f'{model_name}.pth', map_location=torch.device('cpu')))
        #         self.model_target.load_state_dict(torch.load(f'{model_name}_target.pth', map_location=torch.device('cpu')))
        #     else:
        #         self.model.load_state_dict(torch.load(f'{model_name}.pth'))
        #         self.model_target.load_state_dict(torch.load(f'{model_name}_target.pth'))
        #     self.model.eval()
        #     self.model_target.eval()
        # else:
        self.actor_model = self.create_actor_model().to(self.device)
        self.critic_model = self.create_critic_model().to(self.device)

        self.actor_model_target = self.create_actor_model().to(self.device)
        self.actor_model_target.load_state_dict(self.actor_model.state_dict())

        self.critic_model_target = self.create_critic_model().to(self.device)
        self.critic_model_target.load_state_dict(self.critic_model.state_dict())

        self.actor_optimizer = optim.Adam(self.actor_model.parameters(), lr=0.01)
        self.critic_optimizer = optim.Adam(self.critic_model.parameters(), lr = 0.01)

        self.loss_fn = nn.MSELoss()

    def create_actor_model(self):
        return ActorNetwork(self.state_dim, self.action_dim)

    def create_critic_model(self):
        return CriticNetwork(self.state_dim, self.action_dim)

    def remember(self, state, action, reward, next_state, done):
        self.memory.append((state, action, reward, next_state, done))

    def act(self, state, noise = None):
        with torch.no_grad():
            state = torch.tensor(state, dtype=torch.float32).unsqueeze(0).to(self.device)
            action = self.actor_model(state).squeeze(0).detach().cpu().numpy()
            if noise is not None:
                return np.clip(action + noise, a_min=0, a_max=2)
        return action


    def experience_replay(self, batch_size):
        if len(self.memory) < batch_size:
            return  # Not enough samples in memory

        mini_batch = random.sample(self.memory, min(len(self.memory), batch_size))

        for state, action, reward, next_state, done in mini_batch:
            state = torch.tensor(state, dtype=torch.float32).to(self.device)
            next_state = torch.tensor(next_state, dtype=torch.float32).to(self.device)
            action = torch.tensor(action, dtype=torch.float32).to(self.device)

            current_action_q  = self.critic_model(torch.cat((state, action), dim=1))

            with torch.no_grad():
              next_state_q = self.critic_model_target(torch.cat((next_state, self.actor_model_target(next_state)), dim = 1))
              target_q = reward + self.gamma * next_state_q * (1 - done)

            self.critic_optimizer.zero_grad()
            critic_loss = self.loss_fn(current_action_q, target_q)
            critic_loss.backward()
            nn.utils.clip_grad_norm_(self.critic_model.parameters(), 1000)
            self.critic_optimizer.step()

            current_action_q = self.critic_model(torch.cat((state, self.actor_model(state)), dim=1))
            actor_loss = -(current_action_q).mean()

            self.actor_optimizer.zero_grad()
            actor_loss.backward()
            nn.utils.clip_grad_norm_(self.actor_model.parameters(), 1000)
            self.actor_optimizer.step()

        # Update the target model with the new method
        self.update_model_target(self.critic_model, self.critic_model_target)
        self.update_model_target(self.actor_model, self.actor_model_target)


    def update_model_target(self, current, target):
        # Get the state_dict of the current model and the target model
        model_weights = current.state_dict()
        model_target_weights = target.state_dict()

        # Update the weights of the target model
        for key in model_weights:
            model_target_weights[key] = self.tau * model_weights[key] + (1 - self.tau) * model_target_weights[key]

        # Load the updated weights into the target model
        target.load_state_dict(model_target_weights)