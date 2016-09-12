"""
Test bonus evaluators
"""

import logging
import os,sys
import numpy as np
import itertools

from sandbox.pchen.async_rl.async_rl.agents.a3c_agent import A3CAgent
from sandbox.pchen.async_rl.async_rl.agents.dqn_agent import DQNAgent
from sandbox.pchen.async_rl.async_rl.envs.atari_env import AtariEnv
from sandbox.pchen.async_rl.async_rl.algos.a3c_ale import A3CALE
from sandbox.pchen.async_rl.async_rl.algos.dqn_ale import DQNALE
from sandbox.pchen.async_rl.async_rl.utils.get_time_stamp import get_time_stamp
from sandbox.pchen.async_rl.async_rl.utils.ec2_instance import instance_info, subnet_info
from sandbox.pchen.async_rl.async_rl.bonus_evaluators.ale_hashing_bonus_evaluator import ALEHashingBonusEvaluator
from sandbox.pchen.async_rl.async_rl.preprocessor.image_vectorize_preprocessor import ImageVectorizePreprocessor
from sandbox.pchen.async_rl.async_rl.hash.sim_hash import SimHash

from rllab.misc import logger
from rllab.misc.instrument import run_experiment_lite, stub
from rllab import config

stub(globals())

# Running platform
mode = "ec2"
ec2_instance = "c4.8xlarge"
subnet = "us-west-1a"
repetitions = 3 # each repetition uses a different set of random seeds


# Generic setting
rom_dir = "ale_python_interface/roms"
exp_prefix = "async-rl/" + os.path.basename(__file__).split('.')[0] # exp_xxx
snapshot_mode = "last"
plot = False
seeds = None
n_processes = 2

# Problem setting
eval_frequency = 10**5
eval_n_runs = 10
# games = ["pong","freeway","breakout"]
games = ["montezuma_revenge","frostbite","venture"]
agent_types = ["a3c","dqn"]
seeds = None
bonus_coeffs = [0.05,0]
dim_key = 64

if "test" in mode:
    eval_frequency = 200
    eval_n_runs = 1

if "local_docker" in mode:
    actual_mode = "local_docker"
elif "local" in mode:
    actual_mode = "local"
elif "ec2" in mode:
    actual_mode = "ec2"

    # configure instance
    info = instance_info[ec2_instance]
    config.AWS_INSTANCE_TYPE = ec2_instance
    config.AWS_SPOT_PRICE = str(info["price"])
    n_processes = info["vCPU"]

    # choose subnet
    config.AWS_NETWORK_INTERFACES = [
        dict(
            SubnetId=subnet_info[subnet]["SubnetID"],
            Groups=subnet_info[subnet]["Groups"],
            DeviceIndex=0,
            AssociatePublicIpAddress=True,
        )
    ]
else:
    raise NotImplementedError

for idx,game,agent_type,bonus_coeff in \
    itertools.product(range(repetitions),games,agent_types,bonus_coeffs):
    # The meat ---------------------------------------------
    env = AtariEnv(
        rom_filename=os.path.join(rom_dir,game+".bin"),
        plot=plot,
    )
    # preprocessor = ImageVectorizePreprocessor(
    #     n_channel=env.get_img_shape()[0],
    #     width=env.get_img_shape()[1],
    #     height=env.get_img_shape()[2],
    #     slices=[None,None,None],
    # )
    preprocessor = ImageVectorizePreprocessor(
        n_channel=4,
        width=84,
        height=84,
    )
    _hash = SimHash(
        # item_dim=preprocessor.get_output_dim(),
        item_dim=28224,
        dim_key=dim_key,
        bucket_sizes=None,
    )
    bonus_evaluator = ALEHashingBonusEvaluator(
        # state_dim=preprocessor.get_output_dim(),
        state_dim=28224,
        state_preprocessor=preprocessor,
        hash=_hash,
        bonus_coeff=bonus_coeff,
        state_bonus_mode="1/sqrt(n_s)",
        log_prefix="",
        locked_stats=False,
    )

    if agent_type == "a3c":
        agent = A3CAgent(
            n_actions=env.number_of_actions,
            bonus_evaluator=bonus_evaluator,
        )
        algo = A3CALE(
            n_processes=n_processes,
            env=env,
            agent=agent,
            logging_level=logging.INFO,
            eval_frequency=eval_frequency,
            eval_n_runs=eval_n_runs,
            seeds=seeds,
        )
    elif agent_type == "dqn":
        agent = DQNAgent(
            n_actions=env.number_of_actions,
            bonus_evaluator=bonus_evaluator,
        )
        algo = DQNALE(
            n_processes=n_processes,
            env=env,
            agent=agent,
            logging_level=logging.INFO,
            eval_frequency=eval_frequency,
            eval_n_runs=eval_n_runs,
            seeds=seeds,
        )



    # Exp config --------------------------------------------------
    # Exp name
    import datetime
    import dateutil.tz
    now = datetime.datetime.now(dateutil.tz.tzlocal())
    timestamp = now.strftime('%Y%m%d_%H%M%S')
    exp_name = "alex_{time}_{agent_type}_{game}".format(
        time=timestamp,
        agent_type=agent_type,
        game=game,
    )
    if ("ec2" in mode) and (len(exp_name) > 64):
        print("Should not use experiment name with length %d > 64.\nThe experiment name is %s.\n Exit now."%(len(exp_name),exp_name))
        sys.exit(1)


    terminate_machine = not ("test" in mode)

    run_experiment_lite(
        algo.train(),
        exp_prefix=exp_prefix,
        exp_name=exp_name,
        snapshot_mode=snapshot_mode,
        mode=actual_mode,
        sync_s3_pkl=True,
        terminate_machine=terminate_machine,
    )

    if "test" in mode:
        sys.exit(0)

if ("local" not in mode) and ("test" not in mode):
    os.system("chmod 444 %s"%(__file__))
