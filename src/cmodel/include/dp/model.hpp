#pragma once
#include "dp/config.hpp"
#include <boost/multiprecision/cpp_int.hpp>
#include <nlohmann/json.hpp>
#include <cstdint>
#include <memory>
#include <optional>
#include <vector>

namespace dp {
using Big = boost::multiprecision::cpp_int;
using Json = nlohmann::json;
struct Request {
  std::uint64_t id = 0;
  DataType a_type = DataType::FP16, b_type = DataType::FP16;
  CType c_type = CType::FP32;
  ScaleType a_scale_type = ScaleType::NONE, b_scale_type = ScaleType::NONE;
  Big a = 0, b = 0, a_scale = 0, b_scale = 0;
  Big a_e1 = 0, a_e2 = 0, b_e1 = 0, b_e2 = 0;
  std::uint32_t c = 0;
  bool last = false;
};
struct Flags {
  bool invalid = false, overflow = false, underflow = false, inexact = false;
  bool integer_overflow = false, local_truncated = false, global_truncated = false;
};
struct Result {
  std::uint64_t id = 0;
  std::uint32_t bits = 0;
  CType type = CType::FP32;
  bool last = false;
  Flags flags;
  Json trace = Json::array();
};
// Per-request computation uses the exact same stage transitions as Pipeline.
Result evaluate(const Config&, const Request&, bool trace = false);
bool tuple_legal(const Request&);
bool tuple_legal(const Config&, const Request&);
void validate_payload(const Config&, const Request&);
struct State;
struct Tick {
  bool ready = false, accepted = false, protocol_error = false;
  std::optional<Result> output;
  Json registers = Json::array(); // after-edge occupancy / cutpoints, when tracing
};
class Pipeline {
public:
  explicit Pipeline(Config config, bool trace = false);
  ~Pipeline();
  Pipeline(const Pipeline&) = delete;
  Pipeline& operator=(const Pipeline&) = delete;
  // Returns pre-edge output, then advances every occupied stage. Reset cancels all.
  Tick step(const std::optional<Request>& request, bool a_valid, bool b_valid,
            bool c_valid, bool reset = false);
private:
  Config config_;
  bool trace_;
  std::vector<std::unique_ptr<State>> stages_;
};
Config config_from_json(const Json&);
Request request_from_json(const Json&);
Json config_json(const Config&);
Json result_json(const Result&);
Json tick_json(const Tick&);
} // namespace dp
