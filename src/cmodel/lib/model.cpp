#include "detail.hpp"
#include <stdexcept>

// Each occupied software register advances one arithmetic stage per step.
// State retains prior trace data for debugging, not as a hardware register cost.

namespace dp {
void advance(const Config& c,State& s,unsigned stage) {
  s.stage=stage;
  if(c.frontend==Frontend::E && stage<=5) {
    switch(stage) {
      case 1: stage_unpack(c,s); break;
      case 2: e_frontend::stage_pairs(c,s); break;
      case 3: e_frontend::stage_lane_sum(c,s); break;
      case 4: e_frontend::stage_group_sum(c,s); break;
      case 5: e_frontend::stage_scale(c,s,c.post_scale_norm_extra_stage==0); break;
    }
    return;
  }
  if(stage<=4) {
    switch(stage) {
      case 1: stage_unpack(c,s); break;
      case 2: stage_products(c,s); break;
      case 3: stage_local_align(c,s); break;
      case 4: stage_lane_sum(c,s); break;
    }
    return;
  }
  if(stage==5) { stage_group(c,s,c.post_scale_norm_extra_stage==0); return; }
  if(c.post_scale_norm_extra_stage && stage==6) { stage_detect(c,s); return; }
  switch(stage-c.post_scale_norm_extra_stage) {
    case 6: stage_global_align(c,s); break;
    case 7: stage_total(c,s); break;
    case 8: stage_output(c,s); break;
    default: throw std::logic_error("stage outside profile");
  }
}
Result evaluate(const Config& c,const Request& r,bool tracing) {
  c.validate(); validate_payload(c,r);
  State state; state.request=r; state.tracing=tracing;
  for(unsigned stage=1;stage<=c.latency();++stage) advance(c,state,stage);
  return std::move(state.result);
}
Pipeline::Pipeline(Config c,bool tracing):config_(c),trace_(tracing),stages_(c.latency()) { c.validate(); }
Pipeline::~Pipeline()=default;
Tick Pipeline::step(const std::optional<Request>& r,bool av,bool bv,bool cv,bool reset) {
  Tick tick;
  if(reset) { for(auto& s:stages_) s.reset(); return tick; }
  const bool all=av&&bv&&cv;
  tick.protocol_error=all && (!r || !tuple_legal(config_,*r));
  tick.ready=all && !tick.protocol_error; tick.accepted=tick.ready;
  // Payload violations are driver errors. Validate before mutating any pipeline state.
  if(tick.accepted) validate_payload(config_,*r);
  if(stages_.back()) tick.output=std::move(stages_.back()->result);
  for(unsigned index=config_.latency()-1;index>0;--index) {
    stages_[index]=std::move(stages_[index-1]);
    if(stages_[index]) advance(config_,*stages_[index],index+1);
  }
  stages_[0].reset();
  if(tick.accepted) {
    auto state=std::make_unique<State>(); state->request=*r; state->tracing=trace_;
    advance(config_,*state,1); stages_[0]=std::move(state);
  }
  if(trace_) for(unsigned i=0;i<stages_.size();++i) {
    if(stages_[i]) tick.registers.push_back({{"stage",i+1},{"id",stages_[i]->request.id},
      {"datatype",static_cast<unsigned>(stages_[i]->request.a_type)},{"last",stages_[i]->request.last},
      {"cutpoint",stages_[i]->result.trace.back()}});
    else tick.registers.push_back({{"stage",i+1},{"valid",false}});
  }
  return tick;
}
} // namespace dp
