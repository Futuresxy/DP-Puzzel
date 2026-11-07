#include "detail.hpp"

namespace dp {
// Group-local requests retain exactly 64 payload bits, one scale byte,
// four e1 bits and two e2 bits per side. C belongs only to the mixed top.
static Request group_request(const Request &request, unsigned group_index) {
  Request local = request;
  local.a = (request.a >> (64 * group_index)) & mask(64);
  local.b = (request.b >> (64 * group_index)) & mask(64);
  local.a_scale = slice(request.a_scale, 8 * group_index, 8);
  local.b_scale = slice(request.b_scale, 8 * group_index, 8);
  local.a_e1 = slice(request.a_e1, 4 * group_index, 4);
  local.b_e1 = slice(request.b_e1, 4 * group_index, 4);
  local.a_e2 = slice(request.a_e2, 2 * group_index, 2);
  local.b_e2 = slice(request.b_e2, 2 * group_index, 2);
  local.c = 0;
  return local;
}

void stage_mixed_frontends(const Config &config, State &state, unsigned stage) {
  if (stage == 1) {
    state.frontends.resize(config.groups());
    state.participate.resize(config.groups());
    for (unsigned group_index = 0; group_index < config.groups(); ++group_index) {
      state.participate[group_index] = group_index < config.active_groups(state.request.a_type);
      auto &frontend = state.frontends[group_index];
      frontend.request = group_request(state.request, group_index);
      frontend.tracing = state.tracing;
    }
  }
  Json group_traces = Json::array();
  for (unsigned group_index = 0; group_index < config.groups(); ++group_index) {
    Config local = config;
    local.k_fp16 = 4;
    local.frontend = config.group_frontend(group_index);
    auto &frontend = state.frontends[group_index];
    if (state.participate[group_index]) {
      advance(local, frontend, stage);
      if (stage == 5) {
        state.groups.push_back(frontend.groups.at(0));
        state.result.flags.local_truncated |= frontend.result.flags.local_truncated;
      }
      if (state.tracing) group_traces.push_back(frontend.result.trace.back());
    } else {
      if (stage == 5) {
        Token inactive;
        inactive.width = config.group_mag_bits();
        state.groups.push_back(inactive);
      }
      if (state.tracing) group_traces.push_back({{"participate", false}});
    }
  }
  if (stage == 5) finish_group_stage(state, true, Json::array());
  else trace(state, "mixed_group_frontends",
             {{"participate", state.participate}, {"frontends", group_traces}});
}
} // namespace dp
