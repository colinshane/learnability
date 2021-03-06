#!/usr/bin/env python
# -*- coding: utf-8 -*-
from lif import *
from syn import *
from da_stdp import *

timestep = 1.0*ms
neuron_count = 1000
excitatory_count = 800
minimum_excitatory_weight = 0.0
maximum_excitatory_weight = 0.75
inhibitory_weight = -1.0
reward_decay = 0.99
coincidence_window = 20*ms
reward_delay = 0.5*second

def get_params():
    params = LifParams()
    params.update(SynParams())
    params.update(DaStdpParams())
    return params

def setup_network(params):
    neurons = LifNeurons(neuron_count)
    excitatory_synapses = DaStdpSynapses(N)
    excitatory_synapses.connect('i < excitatory_count and i != j', p=connectivity)
    excitatory_synapses.w = 'minimum_excitatory_weight + rand() * (maximum_excitatory_weight - minimum_excitatory_weight)'
    inhibitory_synapses = InhibitorySynapses(N)
    inhibitory_synapses.connect('i >= excitatory_count and i != j', p=connectivity)
    inhibitory_synapses.w = inhibitory_weight
    network = Network()
    network.add(neurons, excitatory_synapses, inhibitory_synapses)
    return neurons, excitatory_synapses, inhibitory_synapses, network

def setup_task(neurons, excitatory_synapses, network, params):
    det_model = '''
    pre_spike : second
    detected : second
    '''
    det_pre = 'pre_spike = t'
    det_post = '''
    set_detected = int(t - pre_spike < coincidence_window)
    detected = detected * (1 - set_detected) + t * set_detected
    '''
    excitatory_synapses.w[0] = 0
    source = excitatory_synapses.i[0]
    target = excitatory_synapses.j[0]
    detector = Synapses(neurons, model=det_model, pre=det_pre, post=det_post, connect='i == source and j == target')
    detector.detected = -reward_delay
    def reward_function(synapses):
        return (synapses.r * reward_decay +
            (reward_amount if int(synapses.t/ms) == int((detector.detected + reward_delay)/ms) else 0))
    reward_unit = RewardUnit(excitatory_synapses, reward_function)
    rate_monitor = PopulationRateMonitor(neurons)
    state_monitor = StateMonitor(excitatory_synapses, ('r', 'l', 'w'), record=[0])
    network.add(detector, reward_unit, rate_monitor, state_monitor)
    return detector, reward_unit, rate_monitor, state_monitor

def run_sim(name, index, duration, input_rate, connectivity, reward_amount):
    prefs.codegen.target = 'weave'
    defaultclock.dt = timestep
    params = get_params()
    params.update({'noise_scale': input_rate,
                   'connectivity': connectivity,
                   'reward_amount': reward_amount})
    print("Simulation {0} Started: duration={1}, input={2}, connectivity={3}, reward={4}".format(
          name, index, duration, input_rate, connectivity, reward_amount))
    neurons, excitatory_synapses, inhibitory_synapses, network = setup_network(params)
    detector, reward_unit, rate_monitor, state_monitor = setup_task(neurons, excitatory_synapses, network, params)
    network.run(duration, report='stdout', report_period=60*second)
    w_post = excitatory_synapses.w
    datafile = open("izhikevich1/{0}_{1}.dat".format(name, index), 'wb')
    numpy.savez(datafile, duration=duration, input_rate=input_rate, connectivity=connectivity, reward_amount=reward_amount,
                w_post=w_post, t=state_monitor.t/second, w0=state_monitor.w[0], l0=state_monitor.l[0],
                rew=state_monitor.r[0], rate=rate_monitor.rate)
    datafile.close()
    print("Simulation Ended")
    return (index, True)

def parallel_function(fn):
    def easy_parallelize(fn, inputs):
        from multiprocessing import Pool
        pool = Pool(processes=4)
        pool.map(fn, inputs)
        pool.close()
        pool.join()
    from functools import partial
    return partial(easy_parallelize, fn)

def packed_run_sim(packed_args):
    run_sim(*packed_args)
run_sim.parallel = parallel_function(packed_run_sim)

def load_sim_data(name, index):
    file = open("izhikevich1/{0}_{1}.dat".format(name, index), 'rb')
    data = numpy.load(file)
    return (data, file)

def plot_sim(name, index):
    from scipy import stats
    data, file = load_sim_data(name, index)
    figure(figsize=(12,12))
    suptitle("Duration: {0}, Input: {1}, Connectivity: {2}, Reward: {3}".format(
          data['duration'], data['input_rate'], data['connectivity'], data['reward_amount']))
    subplot(221)
    plot(data['t'], data['w0'] / w_max)
    plot(data['t'], data['l0'])
    xlabel("Time (s)")
    ylabel("Weight/Eligibility")
    subplot(222)
    plot(data['t'], cumsum(data['rew']))
    xlabel("Time (s)")
    ylabel("Cumulative Reward")
    subplot(223)
    rates = stats.binned_statistic(data['t'], data['rate'], bins=int(data['duration'] / 1.0*second))
    plot(rates[1][1:], rates[0])
    xlabel("Time (s)")
    ylabel("Firing Rate (Hz)")
    subplot(224)
    hist(data['w_post'] / w_max, 20)
    xlabel("Weight / Maximum")
    ylabel("Count")
    show()
    file.close()

def param_search(name):
    from itertools import product, imap, izip
    duration = 1800*second
    input_levels = [0.025, 0.05, 0.1]
    connectivity_levels = [0.05, 0.1, 0.2]
    reward_levels = [1.0]
    num_simulations = len(input_levels) * len(connectivity_levels) * len(reward_levels)
    levels = product(input_levels, connectivity_levels, reward_levels)
    inputs = imap(lambda i,x: (name, index, duration, x[0], x[1], x[2]),
                  range(0, num_simulations), levels)
    run_sim.parallel(inputs)

def plot_param_search(name):
    import os.path
    import scipy.stats
    sim_data = []
    index = 0
    while os.path.exists("izhikevich1/{0}_{1}.dat".format(name, index)):
        sim_data.append(load_sim_data(name, index))
        index += 1
    figure()
    subplot(221)
    for data in sim_data:
        plot(data['t'], data['w0'] / w_max, label="IN: {0} CONN: {1}".format(data['input_rate'], data['connectivity']))
    xlabel("Time (s)")
    ylabel("Target Synapse Weight")
    subplot(222)
    for data in sim_data:
        plot(data['t'], cumsum(data['rew']), label="IN: {0} CONN: {1}".format(data['input_rate'], data['connectivity']))
    xlabel("Time (s)")
    ylabel("Cumulative Reward")
    subplot(223)
    for data in sim_data:
        rates = scipy.stats.binned_statistic(data['t'], data['rate'], bins=int(data['duration'] / 10.0*second))
        plot(rates[1][1:], rates[0], label="IN: {0} CONN: {1}".format(data['input_rate'], data['connectivity']))
    xlabel("Time (s)")
    ylabel("Firing Rate (Hz)")
    subplot(224)
    for data in sim_data:
	    hist(data['w_post'] / w_max, 20, histtype='step')
    xlabel("Weight / Maximum")
    ylabel("Count")
    show()
