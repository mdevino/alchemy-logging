/*  *
 * IBM Confidential
 * OCO Source Materials
 *
 * 5737-C06
 * (C) Copyright IBM Corp. 2017 All Rights Reserved.
 *
 * The source code for this program is not published or otherwise
 * divested of its trade secrets, irrespective of what has been
 * deposited with the U.S. Copyright Office.

 * US Government Users Restricted Rights - Use, duplication or
 * disclosure restricted by GSA ADP Schedule Contract with IBM Corp.

 *
 *  */
/*
 * File description: logger.cpp
 * Author information: Gabe Hart ghart@us.ibm.com
 */
#include "logger.h"

#include <utility>
#include <vector>
#include <ctime>
#include <sstream>
#include <iostream>
#include <iomanip>

#include <boost/locale/encoding_utf.hpp>

using json = nlohmann::json;

namespace logging
{

// Local Only //////////////////////////////////////////////////////////////////

namespace
{

// Implement string splitting to avoid boost dependency:
// CITE: http://stackoverflow.com/questions/236129/split-a-string-in-c
template<typename Out>
void split(const std::string &s, char delim, Out result) {
  std::stringstream ss;
  ss.str(s);
  std::string item;
  while (std::getline(ss, item, delim)) {
    *(result++) = item;
  }
}

std::vector<std::string> split(const std::string &s, char delim) {
  std::vector<std::string> elems;
  split(s, delim, std::back_inserter(elems));
  return elems;
}

detail::CLogChannelRegistrySingleton::FilterMap parseFilterSpec(const std::string& a_spec)
{
  // short-circuit for empty spec
  if (a_spec.empty()) return {{}};

  // Split on comma first
  const auto& splitVec = split(a_spec, ',');

  // Split on ':' and construct the output map
  detail::CLogChannelRegistrySingleton::FilterMap out;
  for (const auto& spec_pair : splitVec)
  {
    const auto& subSplitVec = split(spec_pair, ':');
    if (subSplitVec.size() != 2)
    {
      std::stringstream ss;
      ss << "Invalid Log Spec [" << a_spec << "]";
      throw std::runtime_error(ss.str());
    }
    out[subSplitVec[0]] = detail::ParseLevel(subSplitVec[1]);
  }
  return out;
}

std::string getTimestamp()
{
  std::time_t t = std::time(NULL);
  char timestamp[20]; // Timestamp will always be 20 characters long
  std::strftime(timestamp, sizeof(timestamp), "%Y/%m/%d %H:%M:%S", std::localtime(&t));
  return std::string(timestamp);
}

// CITE: https://stackoverflow.com/questions/15615136/is-codecvt-not-a-std-header
std::string wstring_to_utf8(const std::wstring& str)
{
  return boost::locale::conv::utf_to_utf<char>(str.c_str(), str.c_str() + str.size());
}

} // end anon namespace


// Types and Constants /////////////////////////////////////////////////////////

namespace detail
{

std::ostream& operator<<(std::ostream& a_stream, const detail::ELogLevels& a_level)
{
  static const char* strings[] =
  {
    "OFF ",
    "FATL",
    "ERRR",
    "WARN",
    "INFO",
    "TRCE",
    "DBUG",
    "DBG1",
    "DBG2",
    "DBG3",
    "DBG4",
  };

  if (static_cast< std::size_t >(a_level) < sizeof(strings) / sizeof(*strings))
    a_stream << strings[a_level];
  else
    a_stream << static_cast< int >(a_level);

  return a_stream;
}

std::string LevelToHumanString(const detail::ELogLevels& a_level)
{
  static const char* strings[] =
  {
    "off",
    "fatal",
    "error",
    "warning",
    "info",
    "trace",
    "debug",
    "debug1",
    "debug2",
    "debug3",
    "debug4",
  };

  if (static_cast< std::size_t >(a_level) < sizeof(strings) / sizeof(*strings))
    return strings[a_level];
  else
  {
    std::stringstream ss;
    ss << static_cast< int >(a_level);
    return ss.str();
  }
}

// Get a log level from a string
ELogLevels ParseLevel(const std::string& a_str)
{
  if      (a_str == "off")     return detail::ELogLevels::off;
  else if (a_str == "fatal")   return detail::ELogLevels::fatal;
  else if (a_str == "error")   return detail::ELogLevels::error;
  else if (a_str == "warning") return detail::ELogLevels::warning;
  else if (a_str == "info")    return detail::ELogLevels::info;
  else if (a_str == "trace")   return detail::ELogLevels::trace;
  else if (a_str == "debug")   return detail::ELogLevels::debug;
  else if (a_str == "debug1")  return detail::ELogLevels::debug1;
  else if (a_str == "debug2")  return detail::ELogLevels::debug2;
  else if (a_str == "debug3")  return detail::ELogLevels::debug3;
  else if (a_str == "debug4")  return detail::ELogLevels::debug4;
  else
  {
    std::stringstream ss;
    ss << "Invalid Log Level Spec [" << a_str << "]";
    throw std::runtime_error(ss.str());
    return detail::ELogLevels::error;
  }
}

CLogEntry::CLogEntry(const std::string& a_channel,
                     const ELogLevels a_level,
                     const std::string& a_message,
                     json a_mapData)
  : channel(a_channel),
    level(a_level),
    message(a_message),
    timestamp(getTimestamp()),
    serviceName(logging::detail::CLogChannelRegistrySingleton::instance()->getServiceName()),
    nIndent(logging::detail::CLogChannelRegistrySingleton::instance()->getIndent()),
    threadId(std::this_thread::get_id()),
    mapData(std::move(a_mapData))
{}

// CStdLogFormatter ////////////////////////////////////////////////////////////

std::vector<std::string> CStdLogFormatter::formatEntry(const CLogEntry& a_entry) const
{
  std::vector<std::string> out;

  // Split on newlines
  const auto& splitVec = split(a_entry.message, '\n');

  // Get the format string
  auto format = getHeader(a_entry);

  // NOTE: Filtering is done explicitly in the macro call to avoid the need to
  // allocate a stringstream if the filter fails.
  for (const auto& line : splitVec)
  {
    std::stringstream ss;
    ss << format << line << std::endl << std::flush;
    out.push_back(ss.str());
  }

  // Add map data liens
  for (auto iter = a_entry.mapData.begin(); iter != a_entry.mapData.end(); ++iter)
  {
    std::stringstream ss;
    ss << format << iter.key() << ": " << iter.value() << std::endl << std::flush;
    out.push_back(ss.str());
  }

  return out;
}

std::string CStdLogFormatter::getHeader(const CLogEntry& a_entry) const
{
  std::stringstream ss;

  // Add the timestamp
  ss << a_entry.timestamp;

  // Add the service name if set
  if (not a_entry.serviceName.empty())
  {
    ss << " <" << a_entry.serviceName << ">";
  }

  // Add the channel and level
  std::string ch = a_entry.channel;
  ch.resize(logging::detail::MAX_CHANNEL_LENGTH, ' ');
  ss << " [" << ch << ":" << a_entry.level;
  if (logging::detail::CLogChannelRegistrySingleton::instance()->threadIDEnabled())
  {
    ss << ":" << a_entry.threadId;
  }
  ss << "] ";

  // Add the indent
  for (unsigned i = 0; i < a_entry.nIndent; ++i)
  {
    ss << INDENT_VALUE;
  }

  // Return
  return ss.str();
}

// CJSONLogFormatter ///////////////////////////////////////////////////////////

std::vector<std::string> CJSONLogFormatter::formatEntry(const CLogEntry& a_entry) const
{

  // Start with the arbitrary key/val map
  json j = a_entry.mapData;

  // Add standard fields
  j["channel"] = a_entry.channel;
  j["level_str"] = LevelToHumanString(a_entry.level);
  j["timestamp"] = a_entry.timestamp;
  j["num_indent"] = a_entry.nIndent;

  // Add message if present
  if (not a_entry.message.empty())
  {
    j["message"] = a_entry.message;
  }

  // Add thread id if enabled
  if (logging::detail::CLogChannelRegistrySingleton::instance()->threadIDEnabled())
  {
    std::stringstream ss;
    ss << a_entry.threadId;
    j["thread_id"] = ss.str();
  }

  // Add service name if enabled
  if (not a_entry.serviceName.empty())
  {
    j["service_name"] = a_entry.serviceName;
  }

  // Serialize as output
  return { j.dump() + "\n" };
}

// CLogChannelRegistrySingleton ////////////////////////////////////////////////

CLogChannelRegistrySingleton::Ptr CLogChannelRegistrySingleton::m_pInstance = {};

const CLogChannelRegistrySingleton::Ptr& CLogChannelRegistrySingleton::instance()
{
  if (not m_pInstance)
  {
    m_pInstance = CLogChannelRegistrySingleton::Ptr(new CLogChannelRegistrySingleton());
    m_pInstance->setFormatter(CLogFormatterBase::Ptr(new CStdLogFormatter()));
  }
  return m_pInstance;
}

void CLogChannelRegistrySingleton::setupFilters(const std::string& a_filterSpec,
                                                const std::string& a_defaultLevelSpec)
{
  TLock lock(m_mutex);
  m_filters = parseFilterSpec(a_filterSpec);
  m_defaultLevel = detail::ParseLevel(a_defaultLevelSpec);
}

void CLogChannelRegistrySingleton::addSink(std::basic_ostream<char>& a_sink)
{
  TLock lock(m_mutex);
  m_sinks.push_back(TStreamRef(a_sink));
}

void CLogChannelRegistrySingleton::setFormatter(const CLogFormatterBase::Ptr& a_formatter)
{
  TLock lock(m_mutex);
  m_formatter = a_formatter;
}

void CLogChannelRegistrySingleton::enableThreadID()
{
  TLock lock(m_mutex);
  m_doThreadLog = true;
}

void CLogChannelRegistrySingleton::disableThreadID()
{
  TLock lock(m_mutex);
  m_doThreadLog = false;
}

void CLogChannelRegistrySingleton::setServiceName(const std::string& a_serviceName)
{
  TLock lock(m_mutex);
  m_serviceName = a_serviceName;
}

bool CLogChannelRegistrySingleton::filter(const std::string& a_channel,
                                          ELogLevels a_level) const
{
  if (a_level == logging::detail::ELogLevels::off) {\
    throw std::runtime_error("Logging to 'off' is not allowed");\
    return false;
  } else {
    auto iter = m_filters.find(a_channel);
    return (iter != m_filters.end() ? iter->second : m_defaultLevel) >= a_level;
  }
}

void CLogChannelRegistrySingleton::log(const std::string& a_channel,
                                       ELogLevels a_level,
                                       const std::string& a_msg,
                                       json a_mapData)
{
  // Make sure formatter is set
  if (not m_formatter)
  {
    return;
  }

  // Create the CLogEntry instance
  CLogEntry entry(a_channel, a_level, a_msg, std::move(a_mapData));

  // Iterate through formatted strings
  for (const std::string& line : m_formatter->formatEntry(std::move(entry)))
  {
    // Log to each sink
    for (auto& sink : m_sinks)
    {
      sink.get() << line << std::flush;
    }
  }
}

void CLogChannelRegistrySingleton::log(const std::string& a_channel,
                                       ELogLevels a_level,
                                       const std::wstring& a_msg,
                                       json a_mapData)
{
  log(a_channel, a_level, wstring_to_utf8(a_msg), a_mapData);
}

void CLogChannelRegistrySingleton::addIndent()
{
  TLock lock(m_mutex);
  auto tid = std::this_thread::get_id();
  auto iter = m_indents.find(tid);
  if (iter == m_indents.end())
  {
    m_indents.insert(iter, std::make_pair(tid, 1));
  }
  else
  {
    ++(iter->second);
  }
}

void CLogChannelRegistrySingleton::removeIndent()
{
  TLock lock(m_mutex);
  auto tid = std::this_thread::get_id();
  auto iter = m_indents.find(tid);
  if (iter != m_indents.end() and iter->second > 0)
  {
    --(iter->second);
  }
  if (iter != m_indents.end() and iter->second == 0)
  {
    m_indents.erase(iter);
  }
}

unsigned CLogChannelRegistrySingleton::getIndent() const
{
  auto tid = std::this_thread::get_id();
  auto iter = m_indents.find(tid);
  if (iter == m_indents.end())
  {
    return 0;
  }
  else
  {
    return iter->second;
  }
}

void CLogChannelRegistrySingleton::reset()
{
  TLock lock(m_mutex);
  m_sinks.clear();
  m_filters.clear();
  m_defaultLevel = ELogLevels::off;
  m_doThreadLog = false;
  m_serviceName = "";
  m_indents.clear();
  m_formatter = CLogFormatterBase::Ptr(new CStdLogFormatter());
}

// CLogScope ///////////////////////////////////////////////////////////////////

CLogScope::CLogScope(const std::string& a_logName,
                   ELogLevels a_level,
                   const std::string& a_msg)
  : m_logName(a_logName),
    m_level(a_level),
    m_msg(a_msg)
{
  ALOG_LEVEL_IMPL(m_logName, m_level, "Start: " << m_msg, {});
}

CLogScope::~CLogScope()
{
  ALOG_LEVEL_IMPL(m_logName, m_level, "End: " << m_msg, {});
}

// CLogScopedTimer /////////////////////////////////////////////////////////////

CLogScopedTimer::CLogScopedTimer(const std::string& a_logName,
                                 ELogLevels a_level,
                                 const std::string& a_msg)
  : m_logName(a_logName),
    m_level(a_level),
    m_msg(a_msg),
    m_t0()
{
  if (logging::detail::CLogChannelRegistrySingleton::instance()->filter(m_logName, m_level))
  {
    m_t0 = std::chrono::high_resolution_clock::now();
  }
}

CLogScopedTimer::~CLogScopedTimer()
{
  if (logging::detail::CLogChannelRegistrySingleton::instance()->filter(m_logName, m_level))
  {
    const auto t1 = std::chrono::high_resolution_clock::now();

    float val = 0;
    std::string suffix = "";

    // Start with ns
    val = std::chrono::duration_cast<std::chrono::nanoseconds>(t1-m_t0).count();
    suffix = "ns";

    // [100000000] => seconds
    if (val >= 100000000)
    {
      val = std::chrono::duration<float, std::ratio<1,1>>(t1-m_t0).count();
      suffix = "s";
    }

    // [1000000] => milliseconds
    else if (val >= 1000000)
    {
      val = std::chrono::duration<float, std::ratio<1,1000>>(t1-m_t0).count();
      suffix = "ms";
    }

    // [1000] => microseconds
    else if (val >= 1000)
    {
      val = std::chrono::duration<float, std::ratio<1,1000000>>(t1-m_t0).count();
      suffix = "us";
    }

    // Stream the message
    std::stringstream ss;
    ss << m_msg << val << suffix;
    ALOG_LEVEL_IMPL(m_logName, m_level, ss.str(), {});
  }
}
// CLogScopedIndent ////////////////////////////////////////////////////////////

CLogScopedIndent::CLogScopedIndent()
{
  CLogChannelRegistrySingleton::instance()->addIndent();
}

CLogScopedIndent::~CLogScopedIndent()
{
  CLogChannelRegistrySingleton::instance()->removeIndent();
}

// Init Functions //////////////////////////////////////////////////////////////

void InitLogStream(std::basic_ostream<char>& a_stream)
{
  CLogChannelRegistrySingleton::instance()->addSink(a_stream);
}

std::shared_ptr<std::ofstream> InitLogFile(const std::string& a_filename)
{
  auto out = std::shared_ptr<std::ofstream>(
    new std::ofstream(a_filename + ".log", std::ofstream::out));
  InitLogStream(*out);
  return out;
}

void UseStdFormatter()
{
  CLogChannelRegistrySingleton::instance()->setFormatter(
    CLogFormatterBase::Ptr(new CStdLogFormatter()));
}

void UseJSONFormatter()
{
  CLogChannelRegistrySingleton::instance()->setFormatter(
    CLogFormatterBase::Ptr(new CJSONLogFormatter()));
}

} // end namespace detail
} // end namespace logging
