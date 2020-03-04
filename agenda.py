import abc
from typing import Any, List, Mapping, Tuple

import numpy as np
import yaml

from observation import Observation
from trigger_detector import TriggerDetector, TriggerDetectorLoader


class State:
    # Class naming and describing a state in an agenda.
    
    # TODO String is enough? No, probably has description, at least.
    def __init__(self, name: str, description: str=""):
        self._name = name
        self._description = description
    
    @property
    def name(self):
        return self._name
    
    @property
    def description(self):
        return self._description

    def _to_dict(self):
        return {"name": self._name, "description": self._description}

    @classmethod
    def _from_dict(cls, d):
        return cls(d["name"], d["description"])


class Trigger:
    # Class naming and describing a trigger in an agenda.

    def __init__(self, name: str, description: str=""):
        self._name = name
        self._description = description
    
    @property
    def name(self):
        return self._name
    
    @property
    def description(self):
        return self._description

    def _to_dict(self):
        return {"name": self._name, "description": self._description}

    @classmethod
    def _from_dict(cls, d):
        return cls(d["name"], d["description"])


class Action:
    # Class naming and describing an action used in an agenda.
    # Corresponds to StateMachineDefinition from the v0.1 description.

    # Note: Agenda implementation considers actions to be equal (for purposes
    # of updating the state probabilities and checking how many times an action
    # has been performed).

    def __init__(self, name: str, text: str="", exclusive_flag=True, allowed_repeats=2):
        self._name = name
        self._text = text
        self._exclusive_flag = exclusive_flag
        self._allowed_repeats = allowed_repeats
    
    def __str__(self):
        return "%s: %s" % (self._name, self._text)
    
    @property
    def name(self):
        return self._name
    
    @property
    def text(self):
        return self._text

    @property
    def exclusive_flag(self):
        return self._exclusive_flag
    
    @property
    def allowed_repeats(self):
        return self._allowed_repeats

    def _to_dict(self):
        return {"name": self._name, "text": self._text, "exclusive_flag": self._exclusive_flag, "allowed_repeats": self._allowed_repeats}

    @classmethod
    def _from_dict(cls, d):
        return cls(d["name"], d["text"], d["exclusive_flag"], d["allowed_repeats"])


class Agenda:
    # Class defining all properties of an agenda, but not keeping track of the
    # conversation state. A single Agenda object can be reused between many
    # conversations (Puppeteers). An Agenda object may use language models (from
    # the nlu module) through its trigger detectors, but language models are
    # shared between agendas using the same model.
    
    # TODO Setters and getters for all members

    # TODO Is there any way to use forward type reference here?
    # def __init__(self, name: str, belief_manager: AgendaBeliefManager=None, policy: AgendaPolicy=None):
    def __init__(self, name: str, belief_manager=None, policy=None):
        self._name = name
        if belief_manager is None:
            self._belief_manager = DefaultAgendaBeliefManager(self)
        else:
            self._belief_manager = belief_manager
        if policy is None:
            self._policy = DefaultAgendaPolicy()
        else:
            self._policy = policy
        # TODO Temporary hack to get access to agenda from policy
        self._policy._agenda = self
        # Setting everything else empty to begin with
        self._states = {}
        self._transition_triggers = {}
        self._kickoff_triggers = {}
        self._transitions = {}
        self._start_state_name = None
        self._terminus_names = []
        self._actions = {}
        # TODO Do action maps belong to the AgendaPolicy?
        self._action_map = {}
        self._stall_action_map = {}
        # Do we want to store trigger detectors somewhere else?
        # Separate domain (graph + actions(?)) from detection and policy logic?
        self._kickoff_trigger_detectors = []
        self._transition_trigger_detectors = []

    def _to_dict(self) -> Mapping[str, Any]:
        def to_dict(x):
            if isinstance(x, str):
                return x
            elif isinstance(x, int):
                return x
            elif isinstance(x, float):
                return x
            elif isinstance(x, list):
                return [to_dict(v) for v in x]
            elif isinstance(x, dict):
                return {k: to_dict(v) for (k, v) in x.items()}
            else:
                return x._to_dict()
        field_names = ["_name", "_states", "_transition_triggers",
                       "_kickoff_triggers", "_transitions", "_start_state_name",
                       "_terminus_names", "_actions", "_action_map",
                       "_stall_action_map", "_policy"]
        d = {f[1:]: to_dict(getattr(self, f)) for f in field_names}
        # TODO Anytihng from belief manager?
        return d

    @classmethod
    def _from_dict(cls, d: Mapping[str, Any]) -> type:
        obj = cls(d["name"])
        # Restore all fields, as stored in dict
        for (name, value) in d.items():
            setattr(obj, "_" + name, value)
        # Replace with objects, where appropriate.
        for (name, state) in obj._states.items():
            obj._states[name] = State._from_dict(state)
        for (name, trigger) in obj._transition_triggers.items():
            obj._transition_triggers[name] = Trigger._from_dict(trigger)
        for (name, trigger) in obj._kickoff_triggers.items():
            obj._kickoff_triggers[name] = Trigger._from_dict(trigger)
        for (name, action) in obj._actions.items():
            obj._actions[name] = Action._from_dict(action)
        # TODO Add policy_class parameter to this method.
        obj._policy = DefaultAgendaPolicy._from_dict(obj._policy)
        obj._policy._agenda = obj
        return obj

    @property
    def name(self):
        return self._name

    def add_state(self, state: State):
        self._states[state.name] = state
        self._action_map[state.name] = []
        self._stall_action_map[state.name] = []
        self._transitions[state.name] = {}

    def set_start_state(self, state_name: str):
        self._start_state_name = state_name

    def add_terminus(self, state_name: str):
        self._terminus_names.append(state_name)

    def add_transition_trigger(self, trigger: Trigger):
        self._transition_triggers[trigger.name] = trigger

    def add_kickoff_trigger(self, trigger: Trigger):
        self._kickoff_triggers[trigger.name] = trigger

    def add_transition(self, start_state_name: str, trigger_name: str, end_state_name: str):
        self._transitions[start_state_name][trigger_name] = end_state_name
    
    def add_action_for_state(self, action: Action, state_name: str):
        self._actions[action.name] = action
        self._action_map[state_name].append(action.name)
    
    def add_stall_action_for_state(self, action: Action, state_name: str):
        self._actions[action.name] = action
        self._stall_action_map[state_name].append(action.name)

    def add_transition_trigger_detector(self, trigger_detector: TriggerDetector):
        self._transition_trigger_detectors.append(trigger_detector)

    def add_kickoff_trigger_detector(self, trigger_detector: TriggerDetector):
        self._kickoff_trigger_detectors.append(trigger_detector)

    def store(self, filename: str):
        with open(filename, "w") as file:
            yaml.dump(self._to_dict(), file, default_flow_style=False)

    @classmethod
    def load(cls, filename: str, trigger_detector_loader: TriggerDetectorLoader,
             snips_multi_engine: bool=False) -> type:
        with open(filename, "r") as file:
            d = yaml.load(file)
        agenda = cls._from_dict(d)
        # Load trigger detectors
        # Transition triggers
        trigger_names = list(agenda._transition_triggers.keys())
        detectors = trigger_detector_loader.load(agenda.name, trigger_names, snips_multi_engine=snips_multi_engine)
        print(trigger_names, detectors)
        for detector in detectors:
            agenda.add_transition_trigger_detector(detector)
        # Kickoff triggers
        trigger_names = list(agenda._kickoff_triggers.keys())
        detectors = trigger_detector_loader.load(agenda.name, trigger_names, snips_multi_engine=snips_multi_engine)
        print(trigger_names, detectors)
        for detector in detectors:
            agenda.add_kickoff_trigger_detector(detector)
        return agenda
        
    @property
    def policy(self):
        return self._policy

    @property
    def belief_manager(self):
        return self._belief_manager


class AgendaBelief(abc.ABC):
    # State belief for a single agenda. There will be one AgendaBelief object
    # per conversation and agenda.
    # This abstract class just defines queries to be handled -- queries used by
    # an AgendaPolicy to decisions.
    # Note that AgendaBelief also is responsible for storing kickoff
    # conditions, set by the AgendaBeliefManager based on trigger detectors set
    # in the Agenda.
    # Corresponds to ConversationStateManager from the v0.1 description, for the
    # belief part of th conversation. Load / store to be implemented.

    @abc.abstractmethod
    def kickoff_probability(self, trigger_name: str):
        # Probability that we saw a kickoff trigger in the last observations.
        raise NotImplementedError()

    @abc.abstractproperty
    def non_kickoff_probability(self):
        raise NotImplementedError()

    @abc.abstractproperty
    def error_state_probability(self):
        raise NotImplementedError()

    @abc.abstractproperty
    def non_event_probability(self):
        raise NotImplementedError()

    @abc.abstractproperty
    def reset(self):
        raise NotImplementedError()


class DefaultAgendaBelief(AgendaBelief):
    # A concrete implementation of AgendaBelief, using the same implementation
    # of belief representattion as used in Turducken.

    def __init__(self, agenda: Agenda):
        self._agenda = agenda
        self._transition_probability_map = None
        self._non_event_prob = None
        self._kickoff_probability_map = None
        self._non_kickoff_prob = None
        #self._extractions = {}
        self.reset()
    
    def kickoff_probability(self, trigger_name: str):
        return self._kickoff_probability_map[trigger_name]

    @property
    def non_kickoff_probability(self):
        return self._non_kickoff_prob

    @property
    def error_state_probability(self):
        return self._transition_probability_map["ERROR_STATE"]

    @property
    def non_event_probability(self):
        return self._non_event_prob
    
    # def extraction(self, name: str) -> Any:
    #     if name in self._extractions:
    #         return self._extractions[name]
    #     else:
    #         return None

    def reset(self):
        self._kickoff_probability_map = {tr: 0.0 for tr in self._agenda._kickoff_triggers.keys()}
        self._non_kickoff_prob = 1.0
        self._transition_probability_map = {st: 0.0 for st in self._agenda._states.keys()}
        self._transition_probability_map[self._agenda._start_state_name] = 1.0
        self._transition_probability_map['ERROR_STATE'] = 0.0
        self._non_even_prob = 0.0
    

class AgendaBeliefManager(abc.ABC):
    # An AgendaBeliefManager is responsible for belief update. In the current
    # implementation, every agenda has its own belief manager, but we might want
    # to change to having a common one for all agendas.
    # Corresponds to BeliefManager from the v0.1 description.
    
    @abc.abstractmethod
    def update(self, belief: AgendaBelief, actions: List[Action], observations: List[Observation]):
        raise NotImplementedError()
        
    @abc.abstractmethod
    def create_start_belief(self):
        raise NotImplementedError()


class DefaultAgendaBeliefManager(AgendaBeliefManager):
    # A concrete implementation of AgendaBeliefManager, using the same implementation
    # of belief update as used in Turducken.

    def __init__(self, agenda: Agenda):
        self._agenda = agenda

    def create_start_belief(self):
        return DefaultAgendaBelief(self._agenda)

    def _process_triggers(self, trigger_detectors: List[TriggerDetector],
                          expected_trigger_names: List[str],
                          observations: List[Observation],
                          old_extractions: Mapping[str, Any]) -> Tuple[Mapping[str, float], float, Mapping[str, Any]]:
        trigger_map = {}
        non_trigger_probs = []
        new_extractions = {}
        
        for trigger_detector in trigger_detectors:
            (trigger_map_out, non_trigger_prob, extractions) = trigger_detector.trigger_probabilities(observations, old_extractions)
            print("Got trigger map out:", trigger_map_out)
            new_extractions.update(extractions)
            non_trigger_probs.append(non_trigger_prob)
            for (trigger_name, p) in trigger_map_out.items():
                if trigger_name in expected_trigger_names:
                    if trigger_name not in trigger_map:
                        trigger_map[trigger_name] = p
                    elif trigger_map[trigger_name] < p:
                        trigger_map[trigger_name] = p

        #if non_trigger_probs:
        #    non_trigger_prob = min(non_trigger_probs)
        #else:
        #    non_trigger_prob = 1.0

        # TODO Is this consistent with Turducken's definition of non_event_prob?
        if trigger_map:
            non_trigger_prob = 1.0 - max(trigger_map.values())
        else:
            non_trigger_prob = 1.0
        
        sum_total = sum(trigger_map.values()) + non_trigger_prob
        
        non_trigger_prob = non_trigger_prob / sum_total
        for intent in trigger_map:
            trigger_map[intent] = trigger_map[intent] / sum_total

        print("Final trigger map:", trigger_map)
        print("Non trigger prob:", non_trigger_prob)

        
        return (trigger_map, non_trigger_prob, new_extractions)

    def update(self, belief: DefaultAgendaBelief, actions: List[Action], observations: List[Observation], old_extractions: Mapping[str, Any]) -> Mapping[str, Any]:
        new_extractions = {}
        
        # Handle kickoff triggers.
        (trigger_map, non_trigger_prob, extractions) = self._process_triggers(self._agenda._kickoff_trigger_detectors, self._agenda._kickoff_triggers.keys(), observations, old_extractions)

        # Update kickoff probabilities and extractions
        new_extractions.update(extractions)
        belief._kickoff_probability_map = trigger_map
        belief._non_kickoff_prob = non_trigger_prob

        # Check if the last of the actions taken "belong" to this agenda. Earlier
        # actions may be the finishing actions of a deactivated agenda.
        # TODO What if actions are shared between agendas?
        #if not any([a in self._agenda._actions.values() for a in actions]):
        if actions and not actions[-1] in self._agenda._actions.values():
            return new_extractions

        # Handle transition triggers.
        (trigger_map, non_trigger_prob, extractions) = self._process_triggers(self._agenda._transition_trigger_detectors, self._agenda._transition_triggers.keys(), observations, old_extractions)

        # Update state probabilities and extractions
        new_extractions.update(extractions)
        belief._non_event_prob = non_trigger_prob
        belief._transition_probability_map = self._run_transition_probabilities(belief._transition_probability_map, trigger_map, non_trigger_prob)
        
        return new_extractions

    def _run_transition_probabilities(self, current_probability_map, trigger_map, non_event_prob):
        # Note: This is essentially copied from puppeteer_base, with updated
        #       accesses to the agenda definition through self._agenda.
        """
        Input:
          - current_probability_map: where we left off with the state machine before.
          - trigger_map: events we think were triggered *and* how sure we are that they triggered. Dictionary of dict[event] = prob
          - non_event_prob: probability that we had 0 events.
        Returns:
            - Probability map after new input (e.g. a dicitonary of [state_name] = prob_we_are_in_this_state)
        """

        # Set up our new prob map.
        new_probability_map = {}
        for st in self._agenda._states:
            new_probability_map[st] = 0.0
        new_probability_map['ERROR_STATE'] = 0.0

        # Chance we actually have an event:
        p_event = 1.0 - non_event_prob
        
        # For each state in the machine, do:
        for st in self._agenda._states:
            to_move = current_probability_map[st] * p_event
            new_probability_map[st] = max(0.05, current_probability_map[st] - to_move, new_probability_map[st])
                      
        # For each state in the machine, do:
        for st in self._agenda._states:
            to_move = current_probability_map[st] * p_event
            
            if round(to_move,1) > 0.0:
                for event in trigger_map:
                    trans_prob = to_move * trigger_map[event]
                    if event in self._agenda._transitions[st]:
                        st2 = self._agenda._transitions[st][event]
                        new_probability_map[st2] = new_probability_map[st2] + trans_prob   
                        #_LOGGER.debug("Updating %s prob to %.3f" % (st2, new_probability_map[st2]))
                        # Decrease our confidence that we've had some problems following the script, previously.
                        # Not part of paper.
                        new_probability_map['ERROR_STATE'] = max(0.05, new_probability_map['ERROR_STATE'] - trans_prob)
                    else:
                        # XXX Downgrade our probabilites if we don't have an event that matches a transition?
                        # for this particular state.
                        # Not part of paper.
                        new_probability_map[st] = max(0.05, current_probability_map[st]-trigger_map[event])
                        #_LOGGER.debug("Updating %s prob with downgrade to %.3f" % (st, new_probability_map[st]))                         
                        
                        # Up our confidence that we've had some problems following the script.
                        new_probability_map['ERROR_STATE'] = new_probability_map['ERROR_STATE'] + trans_prob
        
        #for state in new_probability_map:
        #    _LOGGER.info("Prob at end for %s: %.2f" % (state, new_probability_map[state]))
        for state in new_probability_map:
            print("Prob at end for %s: %.2f" % (state, new_probability_map[state]))
        return new_probability_map


class AgendaPolicy(abc.ABC):
    # An agenda policy is responsible for making decisions about how to execute
    # an agenda, most notably by choosing next action(s).
    # Corresponds to ActionManager from the v0.1 description.
    
    @abc.abstractmethod    
    def made_progress(self, belief: AgendaBelief) -> bool:
        raise NotImplementedError()

    @abc.abstractmethod    
    def is_done(self, belief: AgendaBelief) -> bool:
        raise NotImplementedError()

    @abc.abstractmethod    
    def can_kickoff(self, belief: AgendaBelief) -> bool:
        raise NotImplementedError()

    @abc.abstractmethod    
    def pick_actions(self, belief: AgendaBelief, action_history: List[Action], turns_without_progress: int) -> List[Action]:
        raise NotImplementedError()

    @abc.abstractmethod
    def _to_dict(self) -> Mapping[str, Any]:
        raise NotImplementedError()
        
    @abc.abstractclassmethod
    def _from_dict(cls, d: Mapping[str, Any]) -> type:
        raise NotImplementedError()
        
        
class DefaultAgendaPolicy(AgendaPolicy):
    # Default implementaiton of AgendaPolicy, absed on turducken's implementation.
    # The current implementation has one policy object per agenda, as different
    # agendas use different values for the parameters.
    
    # TODO Move parameters to agenda, allowing us to use a common policy object.
    # for all agendas? These parameters feel very specific to this kind of
    # agenda policy though.

    def __init__(self,
                 reuse=False,
                 max_transitions=5,
                 absolute_accept_thresh=0.6,
                 min_accept_thresh_w_differential=0.2,
                 accept_thresh_differential=0.1,
                 # TODO Convention right now: Have to be sure of kickoff.
                 kickoff_thresh=1.0):
        self._reuse = reuse                        # TODO When to use?
        self._max_transitions = max_transitions    # TODO When to use?
        self._absolute_accept_thresh = absolute_accept_thresh
        self._min_accept_thresh_w_differential = min_accept_thresh_w_differential
        self._accept_thresh_differential = accept_thresh_differential
        self._kickoff_thresh = kickoff_thresh
        # TODO Temporary hack to get acces to agenda.
        self._agenda = None


    def _to_dict(self) -> Mapping[str, Any]:
        field_names = ["_reuse", "_max_transitions", "_absolute_accept_thresh",
                       "_min_accept_thresh_w_differential",
                       "_accept_thresh_differential", "_kickoff_thresh"]
        d = {f[1:]: getattr(self, f) for f in field_names}
        return d
    
    @classmethod
    def _from_dict(cls, d: Mapping[str, Any]) -> type:
        return cls(d["reuse"], d["max_transitions"],
                   d["absolute_accept_thresh"],
                   d["min_accept_thresh_w_differential"],
                   d["accept_thresh_differential"],
                   d["kickoff_thresh"])

    def made_progress(self, belief: AgendaBelief) -> bool:
        return belief.non_event_probability <= 0.4 and belief.error_state_probability <= .8

    def is_done(self, belief: AgendaBelief) -> bool:
        best = None
            
        # For state by decresing probabilities that we're in that state. 
        # TODO Probably simpler: just look at best and second-best state
        # TODO Don't access probability map directly
        probability_map = belief._transition_probability_map
        sorted_states = {k: v for k, v in sorted(probability_map.items(), key=lambda item: item[1], reverse=True)}
        for (rank, st) in enumerate(sorted_states):
            if st in self._agenda._terminus_names: 
                # If this is an accept state, we can set our best exit candidate.
                if rank == 0 and probability_map[st] >= self._absolute_accept_thresh:
                    return True
                elif rank == 0 and probability_map[st] >= self._min_accept_thresh_w_differential:
                    best = probability_map[st]
            # If we have an exit candidate, 
            if best != None and rank == 1:
                if best - probability_map[st] >= self._accept_thresh_differential:
                    return True
        return False

    def can_kickoff(self, belief: AgendaBelief) -> bool:
        return 1.0 - belief.non_kickoff_probability >= self._kickoff_thresh

    def pick_actions(self, belief: AgendaBelief, action_history: List[Action], turns_without_progress: int) -> List[Action]:
        current_probability_map = belief._transition_probability_map
        past_action_list = action_history
        
        actions_taken = []
        
        # Action map - maps states to a list of tuples of:
        # (action_name, function, arguments, 
        #  boolean to indicate if this an exclusive action that cannot be used
        #  with other actions, number of allowed repeats for this action)
        if turns_without_progress == 0:
            action_map = self._agenda._action_map
        else:
            action_map = self._agenda._stall_action_map
            
        # Work over the most likely state, to least likely, taking the first
        # actions we are allowed to given repeat allowance & exclusivity.
        # for state by decresing probabilities that we're in that state:
        done = False
        for st in {k: v for k, v in sorted(current_probability_map.items(), key=lambda item: item[1], reverse=True)}:
            # XXX Maybe need to check likeyhood.
            if st in action_map:
                for action_name in action_map[st]:
                    action = self._agenda._actions[action_name]
                    exclusive_flag = action.exclusive_flag
                    allowed_repeats = action.allowed_repeats
                    
                    num_times_action_was_used = past_action_list.count(action)
                    
                    if num_times_action_was_used < allowed_repeats:
                        if exclusive_flag and actions_taken:
                            # Can't do an exclusive action if a non-exclusive
                            # action is already taken.
                            continue

                        actions_taken.append(action)
                        if exclusive_flag:
                            # TODO Skip done flag and return here?
                            done = True
                            break
            if done:
                break
        
        return actions_taken


class PuppeteerPolicyState(abc.ABC):
    # Class holding the conversation-specific state of a policy manager.
    # Corresponds to ConversationStateManager from the v0.1 description, for the
    # policy state part of the conversation. Load / store to be implemented.
    pass


class DefaultPuppeteerPolicyState(abc.ABC):
    # Class holding the conversation-specific state of a policy manager, using
    # the default implementation from turducken.

    def __init__(self, agendas: List[Agenda]):
        self._current_agenda = None
        self._turns_without_progress = {a._name: 0 for a in agendas}
        self._times_made_current = {a._name: 0 for a in agendas}
        self._action_history = {a._name: [] for a in agendas}
        
    def deactivate_agenda(self, agenda_name: str):
        # TODO Turducken currently keeps the history when an agenda is
        # deactivated. Can lead to avoiding states with few actions when an
        # agenda is re-run.
        #self._turns_without_progress[agenda_name] = 0
        #self._action_history[agenda_name] = []
        pass


class PuppeteerPolicyManager(abc.ABC):
    # A puppeteer policy is responsible for selecting the agenda tp run.
    # Corresponds to ConversationOrchestrator from the v0.1 description.

    @abc.abstractmethod
    def act(self, state: PuppeteerPolicyState, beliefs: Mapping[str, AgendaBelief]) -> List[Action]:
        raise NotImplementedError()

    @abc.abstractmethod
    def create_start_state(self) -> PuppeteerPolicyState:
        raise NotImplementedError()
        
        
class DefaultPuppeteerPolicyManager(PuppeteerPolicyManager):
    # Essentially the same policy as run_puppeteer().
    
    def __init__(self, agendas: List[Agenda]):
        self._agendas = agendas
        
    def create_start_state(self) -> PuppeteerPolicyState:
        return DefaultPuppeteerPolicyState(self._agendas)

    def act(self, state: PuppeteerPolicyState, beliefs: Mapping[str, AgendaBelief]) -> List[Action]:
        agenda = state._current_agenda
        last_agenda = None
        actions = []

        if agenda is not None:
            belief = beliefs[agenda._name]
            
            # Update agenda state based on message.
            # What to handle in output?
            progress_flag = agenda.policy.made_progress(belief)
            done_flag = progress_flag and agenda.policy.is_done(belief)
            if progress_flag:
                state._turns_without_progress[agenda.name] = 0
            else:
                # At this point, the current agenda (if there is
                # one) was the one responsible for our previous
                # reply in this convo. Only this agenda has its
                # turns_without_progress counter incremented.
                state._turns_without_progress[agenda.name] += 1
                
            turns_without_progress = state._turns_without_progress[agenda.name]
            
            if turns_without_progress >= 2:
                belief.reset()
                state.deactivate_agenda(agenda.name)
                state._current_agenda = None
            else:
                # Run and see if we get some actions.
                action_history = state._action_history[agenda.name]
                actions = agenda.policy.pick_actions(belief, action_history, turns_without_progress)
                state._action_history[agenda.name].extend(actions)
                
                if not done_flag:
                    # Keep going with this agenda.
                    return actions
                else:
                    # We inactivate this agenda. Will choose a new agenda
                    # in the main while-loop below.
                    # We're either done with the agenda, or had too many turns
                    # without progress.
                    # Do last action if there is one.
                    belief.reset()
                    state.deactivate_agenda(agenda._name)
                    state._current_agenda = None
                    agenda = None
                    last_agenda = agenda
        
        # Try to pick a new agenda.
        for agenda in np.random.permutation(self._agendas):
            belief = beliefs[agenda._name]
            
            if agenda.policy.can_kickoff(belief):
                # TODO When can the agenda be done already here?
                done_flag = agenda.policy.is_done(belief)
                belief.reset()
                kick_off_condition = True
            else:
                kick_off_condition = False

            if agenda == last_agenda or state._times_made_current[agenda._name] > 1:
                # TODO Better to do this before checking for kickoff?
                state.deactivate_agenda(agenda._name)
                belief.reset()
                continue
    
            # IF we kicked off, make this our active agenda, do actions and return.
            if kick_off_condition:
                # Successfully kicked this off.
                # Make this our current agenda.           
                state._current_agenda = agenda
                
                # Do first action.
                # TODO run_puppeteer() uses [] for the action list, not self._action_history
                new_actions = agenda.policy.pick_actions(belief, [], 0)
                actions.extend(new_actions)
                state._action_history[agenda._name].extend(new_actions)

                # TODO This is the done_flag from kickoff. Should check again now?
                if done_flag:
                    state.deactivate_agenda(agenda._name)
                    state._current_agenda = None
                return actions
            else:
                state.deactivate_agenda(agenda._name)
            
        # We failed to take action with an old agenda
        # and failed to kick off a new agenda. We have nothing.
        return actions


class Puppeteer:
    # Main class for an agendas-based conversation.
    # Corresponds to MachineEngine from the v0.1 description.

    def __init__(self, agendas: List[Agenda], policy: PuppeteerPolicyManager=None):
        self._agendas = agendas
        self._beliefs = {a._name: a.belief_manager.create_start_belief() for a in agendas}
        self._last_actions = []
        # TODO We could alternatively use mixins for policies, but changing the
        # policy would require changing the code.
        if policy is None:
            self._policy = DefaultPuppeteerPolicyManager(agendas)
        else:
            self._policy = policy
        self._policy_state = self._policy.create_start_state()
        
    def react(self, observations: List[Observation], old_extractions: Mapping[str, Any]) -> List[Action]:
        new_extractions = {}
        for agenda in self._agendas:
            belief = self._beliefs[agenda._name]
            extractions = agenda.belief_manager.update(belief, self._last_actions, observations, old_extractions)
            new_extractions.update(extractions)
        self._last_actions = self._policy.act(self._policy_state, self._beliefs)
        return (self._last_actions, new_extractions)

    def get_conversation_state(self):
        # Used for storing of conversation state
        # TODO store _beliefs and _last_actions.
        pass

