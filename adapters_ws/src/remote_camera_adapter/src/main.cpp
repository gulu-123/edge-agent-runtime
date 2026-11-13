#include <algorithm>
#include <array>
#include <chrono>
#include <csignal>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <poll.h>
#include <sstream>
#include <stdexcept>
#include <thread>
#include <unistd.h>
#include <vector>
#include <opencv2/imgcodecs.hpp>
#include <rclcpp/rclcpp.hpp>
#include <perception_task_adapter/aruco_detector.hpp>
#include <perception_task_adapter/perception_task_adapter_node.hpp>

namespace {
volatile std::sig_atomic_t stop_requested = 0;
void stop_handler(int) {stop_requested = 1;}
using Clock = std::chrono::steady_clock;
}

int main(int argc, char ** argv)
{
  if (argc < 2) {
    std::cerr << "Usage: remote_camera_adapter RUN_DIRECTORY [--ros-args ...]\n";
    return 2;
  }
  const std::filesystem::path run(argv[1]);
  std::filesystem::create_directories(run / "frames");
  rclcpp::init(argc, argv, rclcpp::InitOptions(), rclcpp::SignalHandlerOptions::None);
  std::signal(SIGINT, stop_handler);
  std::signal(SIGTERM, stop_handler);
  auto node = std::make_shared<perception_task_adapter::PerceptionTaskAdapterNode>();
  const double duration = node->declare_parameter<double>("stream_duration_seconds", 300.0);
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(node);
  std::thread spin([&executor]() {executor.spin();});
  perception_task_adapter::ArucoDetector detector;
  std::vector<unsigned char> buffer;
  const std::array<unsigned char, 2> start_marker{{0xff, 0xd8}};
  const std::array<unsigned char, 2> end_marker{{0xff, 0xd9}};
  std::array<unsigned char, 65536> chunk;
  std::vector<int> previous_ids;
  const auto started = Clock::now();
  auto last_frame = started;
  std::uint64_t frames = 0;
  int result = 0;
  try {
    while (!stop_requested && rclcpp::ok() && !node->finished()) {
      const auto now = Clock::now();
      if (std::chrono::duration<double>(now - started).count() >= duration) {break;}
      const double gap = std::chrono::duration<double>(now - last_frame).count();
      if (gap > (frames == 0 ? 15.0 : 4.0)) {
        throw std::runtime_error("Frame stream stalled; admission stopped");
      }
      pollfd input{STDIN_FILENO, POLLIN, 0};
      const int polled = poll(&input, 1, 200);
      if (polled < 0) {
        if (stop_requested) {break;}
        throw std::runtime_error("poll failed");
      }
      if (polled == 0) {continue;}
      const ssize_t size = read(STDIN_FILENO, chunk.data(), chunk.size());
      if (size == 0) {throw std::runtime_error("Frame stream ended");}
      if (size < 0) {
        if (stop_requested) {break;}
        throw std::runtime_error("Frame stream read failed");
      }
      buffer.insert(buffer.end(), chunk.begin(), chunk.begin() + size);
      if (buffer.size() > 4 * 1024 * 1024) {
        throw std::runtime_error("Frame buffer exceeded four MiB");
      }
      while (!buffer.empty()) {
        const auto first = std::search(buffer.begin(), buffer.end(), start_marker.begin(), start_marker.end());
        if (first == buffer.end()) {
          if (buffer.size() > 1) {buffer.erase(buffer.begin(), buffer.end() - 1);}
          break;
        }
        if (first != buffer.begin()) {buffer.erase(buffer.begin(), first);}
        const auto last = std::search(buffer.begin() + 2, buffer.end(), end_marker.begin(), end_marker.end());
        if (last == buffer.end()) {break;}
        std::vector<unsigned char> jpeg(buffer.begin(), last + 2);
        buffer.erase(buffer.begin(), last + 2);
        const auto frame = cv::imdecode(jpeg, cv::IMREAD_COLOR);
        if (frame.empty()) {throw std::runtime_error("Invalid JPEG in input stream");}
        last_frame = Clock::now();
        ++frames;
        std::vector<int> ids;
        for (const auto & marker : detector.detect(frame)) {ids.push_back(marker.marker_id);}
        const bool submitted = node->process_frame(frame, false);
        const auto received_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(last_frame.time_since_epoch()).count();
        std::cout << "{\"frame\":" << frames << ",\"received_monotonic_ns\":" << received_ns << ",\"ids\":[";
        for (std::size_t i = 0; i < ids.size(); ++i) {
          if (i != 0) {std::cout << ',';}
          std::cout << ids[i];
        }
        std::cout << "],\"submitted\":" << (submitted ? "true" : "false") << ",\"jpeg_bytes\":" << jpeg.size() << "}" << std::endl;
        if (frames == 1 || ids != previous_ids || submitted) {
          std::ostringstream filename;
          filename << "frame-" << std::setw(6) << std::setfill('0') << frames << ".jpg";
          std::ofstream saved(run / "frames" / filename.str(), std::ios::binary);
          saved.write(reinterpret_cast<const char *>(jpeg.data()), static_cast<std::streamsize>(jpeg.size()));
        }
        previous_ids = ids;
      }
    }
    if (node->finished()) {result = node->exit_code();}
  } catch (const std::exception & error) {
    std::cerr << "STREAM_ERROR: " << error.what() << '\n';
    result = 2;
  }
  node->cancel_active();
  executor.cancel();
  spin.join();
  executor.remove_node(node);
  rclcpp::shutdown();
  std::cerr << "STREAM_FINISHED frames=" << frames << " exit=" << result << '\n';
  return result;
}
