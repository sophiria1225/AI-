// Synthetic, text-only exercise of the pinned MiniMax-M3 parser.
// No model, vocabulary, context, tokenizer, sampling, API, or code execution.
#include "parsers/parsers.h"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>

int main(int argc, char ** argv) {
    try {
        if (argc != 2 || std::filesystem::exists(argv[1]))
            throw std::runtime_error("one fresh output path required");
        // A deliberately synthetic template. Directly select the same parser
        // implementation; this does not claim to render a real model prompt.
        common_chat_template tmpl("{% for message in messages %}{{ message['content'] }}{% endfor %}", "", "");
        autoparser::generation_params inputs;
        inputs.messages = json::array({json{{"role", "user"}, {"content", "synthetic parser fixture"}}});
        inputs.tools = json::array({json{{"type", "function"}, {"function", {
            {"name", "execute_python"}, {"description", "Synthetic action; never executed."},
            {"parameters", {{"type", "object"}, {"properties", {{"code", {{"type", "string"}}}}},
                            {"required", json::array({"code"})}, {"additionalProperties", false}}}
        }}}});
        inputs.reasoning_format = COMMON_REASONING_FORMAT_NONE;
        inputs.enable_thinking = false;
        auto data = common_chat_params_init_minimax_m3(tmpl, inputs);
        common_chat_parser_params parser(data);
        parser.parser = std::move(data.parser);
        const std::string ns = "]<]minimax[>[";
        const std::string open = ns + "<tool_call>";
        const std::string invoke = ns + "<invoke name=\"execute_python\">";
        const std::string code = ns + "<code>";
        const std::string code_end = ns + "</code>";
        const std::string invoke_end = ns + "</invoke>";
        const std::string end = ns + "</tool_call>";
        const std::string complete_call = invoke + code + "pass" + code_end + invoke_end;
        const std::vector<std::pair<std::string, std::string>> cases = {
            {"complete_single", open + complete_call + end},
            {"cut_inside_argument", open + invoke + code + "pa"},
            {"cut_after_argument", open + invoke + code + "pass" + code_end},
            {"complete_then_cut", open + complete_call + invoke + code + "pa"},
            {"text_only", "Synthetic text without a tool call."},
        };
        json result{{"synthetic_only", true}, {"uses_real_model_template", false},
            {"format", common_chat_format_name(data.format)},
            {"grammar_nonempty", !data.grammar.empty()}, {"grammar_lazy", data.grammar_lazy},
            {"generation_prompt", data.generation_prompt},
            {"model_loads", 0}, {"vocabulary_loads", 0}, {"inference_contexts", 0},
            {"tokenizations", 0}, {"sampling_calls", 0}, {"environment_calls", 0},
            {"cases", json::array()}};
        for (const auto & entry : cases) {
            json row{{"id", entry.first}, {"synthetic_input", entry.second}, {"parses", json::array()}};
            for (const bool partial : {true, false}) {
                auto message = common_chat_parse(common_chat_input(entry.second), partial, parser);
                json parsed{{"is_partial", partial}, {"tool_calls", json::array()},
                    {"content", message.content}, {"reasoning_characters", message.reasoning_content.size()}};
                for (const auto & call : message.tool_calls) {
                    auto value = json::parse_no_throw(call.arguments);
                    parsed["tool_calls"].push_back(json{{"name", call.name},
                        {"arguments", call.arguments}, {"json_parseable", !value.is_discarded()},
                        {"object_arguments", value.is_object()}});
                }
                row["parses"].push_back(parsed);
            }
            result["cases"].push_back(row);
        }
        std::ofstream output(argv[1]);
        if (!output) throw std::runtime_error("cannot create result");
        output << result.dump(2) << '\n';
        if (!output) throw std::runtime_error("incomplete result write");
        std::cout << "5 synthetic inputs, 10 parser evaluations; no model or tool execution\n";
        return 0;
    } catch (const std::exception & error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
