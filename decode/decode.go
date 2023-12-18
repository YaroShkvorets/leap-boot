package main

import (
	"errors"
	"fmt"
	"io"
	"os"
	"reflect"
	"time"

	firecore "github.com/streamingfast/firehose-core"
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/proto"

	"github.com/golang/protobuf/ptypes"
	pbts "github.com/golang/protobuf/ptypes/timestamp"
	"github.com/pinax-network/firehose-antelope/codec"
	pbantelope "github.com/pinax-network/firehose-antelope/types/pb/sf/antelope/type/v1"
	"github.com/streamingfast/logging"
	"go.uber.org/zap"
)

var fixedTimestamp *pbts.Timestamp

var zlog, tracer = logging.PackageLogger("decoder", "github.com/pinax-network/leap-boot")

func init() {
	logging.InstantiateLoggers()

	fixedTime, _ := time.Parse(time.RFC3339, "2006-01-02T15:04:05Z")
	fixedTimestamp, _ = ptypes.TimestampProto(fixedTime)
}

func main() {

	if len(os.Args) < 3 {
		fmt.Println("Usage: decode <inputFileName> <outputFileName>")
		os.Exit(1)
	}
	inputFileName := os.Args[1]
	outputFileName := os.Args[2]

	// to generate an expected.json file from the dmlog
	generateExpected(inputFileName, outputFileName)
	fmt.Printf("Decoded deep-mind log into JSON file: %s", outputFileName)
}

func writeActualBlocks(actualFile string, blocks []*pbantelope.Block) {
	file, err := os.Create(actualFile)
	noError(err, "Unable to write file %q", actualFile)
	defer file.Close()

	_, err = file.WriteString("[\n")
	noError(err, "Unable to write list start")

	blockCount := len(blocks)
	if blockCount > 0 {
		lastIndex := blockCount - 1
		for i, block := range blocks {
			out, err := MarshalWithOptions(block, "  ", true)
			noError(err, "Unable to marshal block %q", block.AsRef())

			_, err = file.WriteString(out)
			noError(err, "Unable to write block %q", block.AsRef())

			if i != lastIndex {
				_, err = file.WriteString(",\n")
				noError(err, "Unable to write block delimiter %q", block.AsRef())
			}
		}
	}

	_, err = file.WriteString("]\n")
	noError(err, "Unable to write list end")
}

func isNil(v interface{}) bool {
	if v == nil {
		return true
	}

	rv := reflect.ValueOf(v)
	return rv.Kind() == reflect.Ptr && rv.IsNil()
}

func readActualBlocks(filePath string) []*pbantelope.Block {
	blocks := []*pbantelope.Block{}

	file, err := os.Open(filePath)
	noError(err, "Unable to open actual blocks file %q", filePath)
	defer file.Close()

	lineChannel := make(chan string)

	consoleReader, err := codec.NewConsoleReader(lineChannel, firecore.NewBlockEncoder(), zlog, tracer)
	if err != nil {
		zlog.Fatal("failed to init console reader", zap.Error(err))
	}

	go func() {
		err := consoleReader.(*codec.ConsoleReader).ProcessData(file)
		if !errors.Is(err, io.EOF) {
			noError(err, "Error reading file %q", filePath)
		}
	}()

	var reader = func() (interface{}, error) {
		out, err := consoleReader.ReadBlock()
		if err != nil {
			return nil, err
		}

		pbBlock := &pbantelope.Block{}
		err = out.Payload.UnmarshalTo(pbBlock)
		if err != nil {
			return nil, err
		}

		return pbBlock, nil
	}

	var lastBlockRead *pbantelope.Block
	for {
		out, err := reader()
		if v, ok := out.(proto.Message); ok && !isNil(v) {

			block := sanitizeBlock(out.(*pbantelope.Block))
			blocks = append(blocks, block)
			lastBlockRead = block
		}

		if err == io.EOF {
			break
		}

		if err != nil {
			if lastBlockRead == nil {
				noError(err, "Unable to read first block from file %q", filePath)
			} else {
				noError(err, "Unable to read block from file %q, last block read was %s", lastBlockRead.AsRef())
			}
		}
	}

	return blocks
}

func sanitizeBlock(block *pbantelope.Block) *pbantelope.Block {
	var sanitizeContext func(logContext *pbantelope.Exception_LogContext)
	sanitizeContext = func(logContext *pbantelope.Exception_LogContext) {
		if logContext != nil {
			logContext.Line = 666
			logContext.ThreadName = "thread"
			logContext.Timestamp = fixedTimestamp
			sanitizeContext(logContext.Context)
		}
	}

	sanitizeException := func(exception *pbantelope.Exception) {
		if exception != nil {
			for _, stack := range exception.Stack {
				sanitizeContext(stack.Context)
			}
		}
	}

	sanitizeRLimitOp := func(rlimitOp *pbantelope.RlimitOp) {
		switch v := rlimitOp.Kind.(type) {
		case *pbantelope.RlimitOp_AccountUsage:
			v.AccountUsage.CpuUsage.LastOrdinal = 111
			v.AccountUsage.NetUsage.LastOrdinal = 222
		case *pbantelope.RlimitOp_State:
			v.State.AverageBlockCpuUsage.LastOrdinal = 333
			v.State.AverageBlockNetUsage.LastOrdinal = 444
		}
	}

	for _, rlimitOp := range block.RlimitOps {
		sanitizeRLimitOp(rlimitOp)
	}

	for _, trxTrace := range block.UnfilteredTransactionTraces {
		trxTrace.Elapsed = 888
		sanitizeException(trxTrace.Exception)

		for _, permOp := range trxTrace.PermOps {
			if permOp.OldPerm != nil {
				permOp.OldPerm.LastUpdated = fixedTimestamp
			}

			if permOp.NewPerm != nil {
				permOp.NewPerm.LastUpdated = fixedTimestamp
			}
		}

		for _, rlimitOp := range trxTrace.RlimitOps {
			sanitizeRLimitOp(rlimitOp)
		}

		for _, actTrace := range trxTrace.ActionTraces {
			actTrace.Elapsed = 999
			sanitizeException(actTrace.Exception)
		}

		if trxTrace.FailedDtrxTrace != nil {
			sanitizeException(trxTrace.FailedDtrxTrace.Exception)
			for _, actTrace := range trxTrace.FailedDtrxTrace.ActionTraces {
				sanitizeException(actTrace.Exception)
			}
		}
	}

	return block
}

func generateExpected(dmlogFile, expectedJsonFile string) {

	actualBlocks := readActualBlocks(dmlogFile)
	zlog.Info("read all blocks from dmlog file", zap.Int("block_count", len(actualBlocks)), zap.String("file", dmlogFile))

	writeActualBlocks(expectedJsonFile, actualBlocks)

	// err := compressFile(expectedJsonFile)
	// noError(err, "Unable to compress file %q", expectedJsonFile)
}

func MarshalWithOptions(m proto.Message, indent string, emitUnpopulated bool) (string, error) {
	res, err := protojson.MarshalOptions{Indent: indent, EmitUnpopulated: emitUnpopulated}.Marshal(m)
	if err != nil {
		return "", err
	}

	return string(res), err
}

func noError(err error, message string, args ...interface{}) {
	if err != nil {
		quit(message+": "+err.Error(), args...)
	}
}

func ensure(condition bool, message string, args ...interface{}) {
	if !condition {
		quit(message, args...)
	}
}

func quit(message string, args ...interface{}) {
	fmt.Printf(message+"\n", args...)
	os.Exit(1)
}
