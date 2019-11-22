
// Standard
import { Writable } from 'stream';

// Third Party
import { expect } from 'chai';
import MemoryStreams from 'memory-streams';
const deepEqual = require('deep-equal');

// Things under test (will be monkey patched)
const rewire = require('rewire');
const alog  = rewire('../src');
const isLogCode = alog.__get__('isLogCode');
const AlogCoreSingleton = alog.__get__('AlogCoreSingleton');
const PrettyFormatter = alog.__get__('PrettyFormatter');
const JsonFormatter = alog.__get__('JsonFormatter');
const nameFromLevel = alog.__get__('nameFromLevel');

/*-- Helpers -----------------------------------------------------------------*/

const IS_PRESENT = '__is_present__';

// How do you log errors when testing a logger??
function testFailureLog(msg: string): void {
  process.stderr.write(`** ${msg} \n`);
}

// Helper that validates an indivitual log record against expected values.
// If the value in the expected record is IS_PRESENT, then it just checks
// for the presence of the field, otherwise, it checks for equality.
function validateLogRecord(record: any, expected: any): boolean {

  let res = true;

  // Validate all expected keys
  for (const expKey of Object.keys(expected)) {
    const expValue = expected[expKey];
    if (expValue === IS_PRESENT) {
      if (!record.hasOwnProperty(expKey)) {
        testFailureLog(`Missing expected key ${expKey}`);
        res = false;
      }
    } else if (expKey === 'metadata' && ! deepEqual(expValue, record.metadata)) {
      testFailureLog(
        `Record mismatch [metadata]. Exp: ${JSON.stringify(expValue)}, Got: ${JSON.stringify(record.metadata)}`);
      res = false;
    } else if (expKey !== 'metadata' && record[expKey] !== expValue) {
      testFailureLog(`Record mismatch [${expKey}]. Exp: ${expValue}, Got: ${record[expKey]}`);
      res = false;
    }
  }

  // Make sure there are no unexpected keys
  for (const gotKey of Object.keys(record)) {
    if (!Object.keys(expected).includes(gotKey)) {
      testFailureLog(`Got unexpected key: ${gotKey}`);
      res = false;
    }
  }

  return res;
}

// Wrapper to run validateLogRecord against multiple lines
function validateLogRecords(records: any[], expecteds: any[]): boolean {

  let res = true;

  // Make sure the lengths are the same
  if (records.length !== expecteds.length) {
    testFailureLog(`Length mismatch. Exp: ${expecteds.length}, Got: ${records.length}`);
    res = false;
  }

  // Iterate the lines and compare in parallel
  const iterSize = Math.min(records.length, expecteds.length);
  for (let i = 0; i < iterSize; i++) {
    if (!validateLogRecord(records[i], expecteds[i])) {
      testFailureLog(`Line mismatch on ${i}`);
      res = false;
    }
  }
  return res;
}

const sampleLogCode = '<TST00000000I>';

/*-- Tests -------------------------------------------------------------------*/

describe("Alog TypeScript Test Suite", () => {
  // core singleton suite
  describe("AlogCoreSingleton", () => {

    describe("mutators", () => {
      const alogCore = AlogCoreSingleton.getInstance();
      beforeEach(() => {
        alogCore.reset();
      });

      it("should be able to set the default level", () => {
        expect((alogCore as any).defaultLevel).to.equal(alog.OFF);
        alogCore.setDefaultLevel(alog.DEBUG);
        expect((alogCore as any).defaultLevel).to.equal(alog.DEBUG);
      });

      it("should be able to set filters", () => {
        expect((alogCore as any).defaultLevel).to.equal(alog.OFF);
        alogCore.setFilters({TEST: alog.INFO});
        expect((alogCore as any).filters).to.deep.equal({TEST: alog.INFO});
      });

      it("should be able to set the formatter", () => {
        expect((alogCore as any).formatter.name).to.equal(PrettyFormatter.name);
        alogCore.setFormatter(JsonFormatter);
        expect((alogCore as any).formatter.name).to.equal(JsonFormatter.name);
      });

      it("should be able to indent", () => {
        expect((alogCore as any).numIndent).to.equal(0);
        alogCore.indent();
        expect((alogCore as any).numIndent).to.equal(1);
      });

      it("should be able to deindent", () => {
        expect((alogCore as any).numIndent).to.equal(0);
        alogCore.indent();
        expect((alogCore as any).numIndent).to.equal(1);
        alogCore.deindent();
        expect((alogCore as any).numIndent).to.equal(0);
      });

      it("should be not able to deindent past 0", () => {
        expect((alogCore as any).numIndent).to.equal(0);
        alogCore.deindent();
        expect((alogCore as any).numIndent).to.equal(0);
      });

      it("should be able to add metadata", () => {
        expect((alogCore as any).metadata).to.deep.equal({});
        alogCore.addMetadata('key', {nested: 1});
        expect((alogCore as any).metadata).to.deep.equal({key: {nested: 1}});
      });

      it("should be able to remove metadata", () => {
        expect((alogCore as any).metadata).to.deep.equal({});
        alogCore.addMetadata('key', {nested: 1});
        expect((alogCore as any).metadata).to.deep.equal({key: {nested: 1}});
        alogCore.removeMetadata('key');
        expect((alogCore as any).metadata).to.deep.equal({});
      });

      it("should ignore request to remove unknown metadata", () => {
        expect((alogCore as any).metadata).to.deep.equal({});
        alogCore.addMetadata('key', {nested: 1});
        expect((alogCore as any).metadata).to.deep.equal({key: {nested: 1}});
        alogCore.removeMetadata('foobar');
        expect((alogCore as any).metadata).to.deep.equal({key: {nested: 1}});
      });

      it("should be able to add a custom stream", () => {
        expect((alogCore as any).streams.length).to.equal(1);
        alogCore.addOutputStream(new MemoryStreams.WritableStream());
        expect((alogCore as any).streams.length).to.equal(2);
      });

      it("should be able to reset output streams", () => {
        expect((alogCore as any).streams.length).to.equal(1);
        alogCore.addOutputStream(new MemoryStreams.WritableStream());
        expect((alogCore as any).streams.length).to.equal(2);
        alogCore.resetOutputStreams();
        expect((alogCore as any).streams.length).to.equal(1);
      });
    }); // mutators

    describe("isEnabled", () => {
      const alogCore = AlogCoreSingleton.getInstance();
      beforeEach(() => {
        alogCore.reset();
        alogCore.setDefaultLevel(alog.DEBUG);
        alogCore.setFilters({LOWER: alog.INFO, HIGHER: alog.DEBUG2});
      });

      it("should return enabled false using the default level", () => {
        expect(alogCore.isEnabled('TEST', alog.DEBUG4)).to.be.false;
      });

      it("should return enabled true using the default level", () => {
        expect(alogCore.isEnabled('TEST', alog.DEBUG)).to.be.true;
      });

      it("should return enabled false using a filter lower than the default", () => {
        expect(alogCore.isEnabled('LOWER', alog.DEBUG)).to.be.false;
      });

      it("should return enabled true using a filter lower than the default", () => {
        expect(alogCore.isEnabled('LOWER', alog.WARNING)).to.be.true;
      });

      it("should return enabled false using a filter higher than the default", () => {
        expect(alogCore.isEnabled('HIGHER', alog.DEBUG3)).to.be.false;
      });

      it("should return enabled true using a filter higher than the default", () => {
        expect(alogCore.isEnabled('HIGHER', alog.DEBUG1)).to.be.true;
      });
    }); // isEnabled

    describe("log", () => {

      const alogCore = AlogCoreSingleton.getInstance();
      let logStream: Writable;
      beforeEach(() => {
        alogCore.reset();
        alogCore.setDefaultLevel(alog.DEBUG);
        alogCore.setFilters({LOWER: alog.INFO, HIGHER: alog.DEBUG2});
        alogCore.setFormatter(JsonFormatter);
        logStream = new MemoryStreams.WritableStream();
        alogCore.addOutputStream(logStream);
      });

      function getLogRecords(): string[] {
        return logStream.toString().split('\n').filter(
          (line) => line !== '').map(
          (line) => JSON.parse(line));
      }

      it("should be able to log with signature 1", () => {
        alogCore.log(alog.DEBUG, 'TEST', sampleLogCode, () => "This is a generated message", {foo: 'bar'});
        alogCore.log(alog.INFO, 'FOO', sampleLogCode, () => "This is a second generated message");
        expect(validateLogRecords(getLogRecords(), [
          {
            channel: 'TEST', level: alog.DEBUG, level_str: nameFromLevel[alog.DEBUG],
            timestamp: IS_PRESENT, num_indent: 0,
            message: "This is a generated message",
            metadata: {foo: 'bar'},
            log_code: sampleLogCode,
          },
          {
            channel: 'FOO', level: alog.INFO, level_str: nameFromLevel[alog.INFO],
            timestamp: IS_PRESENT, num_indent: 0,
            message: "This is a second generated message",
            log_code: sampleLogCode,
          },
        ])).to.be.true;
      });

      it("should be able to log with signature 2", () => {
        //DEBUG
      });

      it("should be able to log with signature 3", () => {
        //DEBUG
      });

      it("should be able to log with signature 4", () => {
        //DEBUG
      });

    });

  }); // AlogCoreSingleton

  // custom stream suite
  describe("Custom Stream Test Suite", () => {
    it("Should attach an output string stream", () => {
      //DEBUG
    });
  });
  // configure suite

  // pretty print suite

  // json suite

  // input validation suite
  describe("Input validation suite", () => {
    // Checks for verifying that log codes are valid or invalid
    describe("Log Code Validation", () => {
      it("A happy log code is valid", () => {
        expect(isLogCode("<ORC12345678D>")).to.be.true;
      });

      it("A log code that is missing its starting angle bracket should fail", () => {
        expect(isLogCode("ORC12345678D>")).to.be.false;
      });

      it("A log code that is missing its closing angle bracket should fail", () => {
        expect(isLogCode("<ORC12345678D")).to.be.false;
      });

      it("A log code that has more than 8 digits should fail", () => {
        expect(isLogCode("<ORC1234544242678D>")).to.be.false;
      });

      it("A log code that has less than 8 digits should fail", () => {
        expect(isLogCode("<ORC178D>")).to.be.false;
      });

      it("A log code that has lowercase letters should fail", () => {
        expect(isLogCode("<orc12345678D>")).to.be.false;
      });

      it("A log code that has a lowercase letter for its level key should fail", () => {
        expect(isLogCode("<ORC12345678d>")).to.be.false;
      });

      it("A log code that is missing a level key should fail", () => {
        expect(isLogCode("<ORC12345678>")).to.be.false;
      });

      it("A log code that has a level key that is not in {IWTDEF} should fail", () => {
        expect(isLogCode("<ORC12345678Z>")).to.be.false;
      });
    });
  });

  // child logger stuff suite
});
