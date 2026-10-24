// Synthetic token IDs only. No vocabulary, model, neural inference or tools.
#include "reasoning-budget.h"
#include "llama.h"
#include "ggml.h"
#include "json.h"

#include <cmath>
#include <cstdio>
#include <vector>

using json = common_json;
constexpr llama_token START = 100;
constexpr llama_token END = 101;
constexpr llama_token PAYLOAD = 7;
constexpr int BUDGET = 2048;

struct trial {
    llama_sampler * sampler;
    int accepted = 0;
    int payload = 0;
    int forced = 0;
    int starts = 0;
    int applies = 0;

    trial() : sampler(common_reasoning_budget_init(nullptr, {{START}}, {{END}}, {END},
                       BUDGET, REASONING_BUDGET_COUNTING)) {}
    ~trial() { llama_sampler_free(sampler); }

    llama_token forced_token() {
        std::vector<llama_token_data> candidates;
        for (int id = 0; id <= END; ++id) candidates.push_back({id, 0.0f, 0.0f});
        llama_token_data_array array{candidates.data(), candidates.size(), -1, false};
        llama_sampler_apply(sampler, &array); ++applies;
        int finite = 0; llama_token token = LLAMA_TOKEN_NULL;
        for (auto & candidate : candidates) {
            if (std::isfinite(candidate.logit)) { ++finite; token = candidate.id; }
        }
        GGML_ASSERT(finite == 1 || finite == END + 1);
        return finite == 1 ? token : LLAMA_TOKEN_NULL;
    }

    void accept(llama_token token, bool expect_forcing = false) {
        auto selected = forced_token();
        GGML_ASSERT(expect_forcing ? selected == token : selected == LLAMA_TOKEN_NULL);
        llama_sampler_accept(sampler, token); ++accepted;
        payload += token == PAYLOAD; starts += token == START; forced += expect_forcing;
    }

    void fill(int count) { for (int i = 0; i < count; ++i) accept(PAYLOAD); }
    void expect(common_reasoning_budget_state state) {
        GGML_ASSERT(common_reasoning_budget_get_state(sampler) == state);
    }
    json result(const char * name, const char * state, int global_limit = -1) {
        return json{{"case", name}, {"budget_per_block", BUDGET},
            {"synthetic_global_output_limit", global_limit}, {"accepted_synthetic_tokens", accepted},
            {"synthetic_payload_tokens", payload}, {"forced_end_tokens", forced},
            {"new_start_tokens", starts}, {"sampler_apply_calls", applies},
            {"state_at_end", state}, {"uses_real_vocabulary", false}};
    }
};

int main() {
    json results = json::array();
    {
        trial t; t.fill(8); t.accept(END); t.expect(REASONING_BUDGET_DONE);
        GGML_ASSERT(t.forced_token() == LLAMA_TOKEN_NULL);
        results.push_back(t.result("natural_end_before_budget", "DONE"));
    }
    {
        trial t; t.fill(BUDGET); t.expect(REASONING_BUDGET_FORCING);
        t.accept(END, true); t.expect(REASONING_BUDGET_DONE);
        GGML_ASSERT(t.forced_token() == LLAMA_TOKEN_NULL);
        results.push_back(t.result("one_full_block_then_forced_end", "DONE"));
    }
    {
        trial t; t.fill(BUDGET); t.accept(END, true); t.expect(REASONING_BUDGET_DONE);
        t.accept(START); t.expect(REASONING_BUDGET_COUNTING);
        t.fill(4096 - t.accepted); t.expect(REASONING_BUDGET_COUNTING);
        GGML_ASSERT(t.accepted == 4096 && t.payload == 4094 && t.forced == 1);
        results.push_back(t.result("reopened_block_at_total_limit", "COUNTING", 4096));
    }
    {
        trial t; t.fill(1024); t.expect(REASONING_BUDGET_COUNTING);
        GGML_ASSERT(t.forced == 0);
        results.push_back(t.result("total_limit_smaller_than_block_budget", "COUNTING", 1024));
    }
    printf("%s\n", json{{"synthetic_cases", results}, {"model_forward_passes", 0},
        {"model_generations", 0}, {"vocabulary_loads", 0}, {"tokenizations", 0},
        {"environment_api_requests", 0}, {"task_evaluations", 0},
        {"limitations", "Handwritten token IDs and logits. No real UTF-8 token pieces, HTTP request path, model outputs, task quality or whole-task savings are tested."}}.dump(2).c_str());
}
