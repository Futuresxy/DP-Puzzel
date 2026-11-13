#include "detail.hpp"
#include <stdexcept>

// Each occupied software register advances one arithmetic stage per step.
// State retains prior trace data for debugging, not as a hardware register cost.

namespace dp {
void advance(const Config &config, State &state, unsigned stage) {
  state.stage = stage;
  if (stage == 1) state.baseline_v18 = config.baseline_v18();
  if (config.mixed() && stage <= 5) {
    stage_mixed_frontends(config, state, stage);
    return;
  }
  if (config.frontend == Frontend::E && stage <= 5) {
    switch (stage) {
    case 1:
      stage_unpack(config, state);
      break;
    case 2:
      e_frontend::stage_pairs(config, state);
      break;
    case 3:
      e_frontend::stage_lane_sum(config, state);
      break;
    case 4:
      e_frontend::stage_group_sum(config, state);
      break;
    case 5:
      e_frontend::stage_scale(config, state, config.post_scale_norm_extra_stage == 0);
      break;
    }
    return;
  }
  if (stage <= 4) {
    switch (stage) {
    case 1:
      stage_unpack(config, state);
      break;
    case 2:
      if (config.frontend == Frontend::Q) q_frontend::stage_products(config, state);
      else if (config.frontend == Frontend::QE) qe_frontend::stage_products(config, state);
      else stage_products(config, state);
      break;
    case 3:
      stage_local_align(config, state);
      break;
    case 4:
      stage_lane_sum(config, state);
      break;
    }
    return;
  }
  if (stage == 5) {
    if (config.frontend == Frontend::Q)
      q_frontend::stage_group(config, state, config.post_scale_norm_extra_stage == 0);
    else if (config.frontend == Frontend::QE)
      qe_frontend::stage_group(config, state, config.post_scale_norm_extra_stage == 0);
    else stage_group(config, state, config.post_scale_norm_extra_stage == 0);
    return;
  }
  if (config.post_scale_norm_extra_stage && stage == 6) {
    stage_detect(config, state);
    return;
  }
  switch (stage - config.post_scale_norm_extra_stage) {
  case 6:
    stage_global_align(config, state);
    break;
  case 7:
    stage_total(config, state);
    break;
  case 8:
    stage_output(config, state);
    break;
  default:
    throw std::logic_error("stage outside profile");
  }
}
Result evaluate(const Config &config, const Request &request, bool tracing) {
  config.validate();
  validate_payload(config, request);
  State state;
  state.request = request;
  state.tracing = tracing;
  for (unsigned stage = 1; stage <= config.latency(); ++stage)
    advance(config, state, stage);
  return std::move(state.result);
}
Pipeline::Pipeline(Config config, bool tracing)
    : config_(config), trace_(tracing), stages_(config.latency()) {
  config.validate();
}
Pipeline::~Pipeline() = default;
Tick Pipeline::step(const std::optional<Request> &request, bool a_valid, bool b_valid, bool c_valid,
                    bool reset_requested) {
  Tick tick;
  if (reset_requested) {
    for (auto &state : stages_)
      state.reset();
    return tick;
  }
  const bool all_valid = a_valid && b_valid && c_valid;
  tick.protocol_error = all_valid && (!request || !tuple_legal(config_, *request));
  tick.ready = all_valid && !tick.protocol_error;
  tick.accepted = tick.ready;
  // Payload violations are driver errors. Validate before mutating any pipeline state.
  if (tick.accepted)
    validate_payload(config_, *request);
  if (stages_.back())
    tick.output = std::move(stages_.back()->result);
  for (unsigned index = config_.latency() - 1; index > 0; --index) {
    stages_[index] = std::move(stages_[index - 1]);
    if (stages_[index])
      advance(config_, *stages_[index], index + 1);
  }
  stages_[0].reset();
  if (tick.accepted) {
    auto state = std::make_unique<State>();
    state->request = *request;
    state->tracing = trace_;
    advance(config_, *state, 1);
    stages_[0] = std::move(state);
  }
  if (trace_)
    for (unsigned stage_index = 0; stage_index < stages_.size(); ++stage_index) {
      if (stages_[stage_index])
        tick.registers.push_back(
            {{"stage", stage_index + 1},
             {"id", stages_[stage_index]->request.id},
             {"datatype", static_cast<unsigned>(stages_[stage_index]->request.a_type)},
             {"last", stages_[stage_index]->request.last},
             {"cutpoint", stages_[stage_index]->result.trace.back()}});
      else
        tick.registers.push_back({{"stage", stage_index + 1}, {"valid", false}});
    }
  return tick;
}
} // namespace dp
