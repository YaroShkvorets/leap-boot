package main

import (
	"encoding/json"
	"fmt"
	"github.com/streamingfast/bstream"
	firecore "github.com/streamingfast/firehose-core"
	pbbstream "github.com/streamingfast/pbgo/sf/bstream/v1"
	"google.golang.org/protobuf/proto"
	"io"
	"io/ioutil"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/golang/protobuf/ptypes"
	pbts "github.com/golang/protobuf/ptypes/timestamp"
	"github.com/klauspost/compress/zstd"
	"github.com/lithammer/dedent"
	"github.com/manifoldco/promptui"
	"github.com/pinax-network/firehose-antelope/codec"
	pbantelope "github.com/pinax-network/firehose-antelope/types/pb/sf/antelope/type/v1"
	"github.com/streamingfast/jsonpb"
	"github.com/streamingfast/logging"
	"github.com/stretchr/testify/assert"
	"go.uber.org/zap"
	"golang.org/x/crypto/ssh/terminal"
)

var fixedTimestamp *pbts.Timestamp

var zlog, tracer = logging.PackageLogger("battlefield", "github.com/pinax-network/leap-boot")

func init() {
	logging.InstantiateLoggers()

	bstream.InitGeneric("EOS", 1, func() proto.Message {
		return new(pbantelope.Block)
	})

	fixedTime, _ := time.Parse(time.RFC3339, "2006-01-02T15:04:05Z")
	fixedTimestamp, _ = ptypes.TimestampProto(fixedTime)
}

func main() {

	// to generate an expected.json file from the dmlog
	// generateExpected("dm.log", "expected.json")
	// return

	ensure(len(os.Args) == 2, "Single argument must be <chain> to compare")
	chain := os.Args[1]

	actualDmlogFile := filepath.Join("run", "syncer-"+chain+".dmlog")
	actualJSONFile := filepath.Join("run", "syncer-"+chain+".json")
	expectedJSONFile := filepath.Join("run", "data", "oracle", chain, "expected.json")

	err := uncompressFile(expectedJSONFile)
	noError(err, "unable to uncompress file")

	actualBlocks := readActualBlocks(actualDmlogFile)
	zlog.Info("read all blocks from dmlog file", zap.Int("block_count", len(actualBlocks)), zap.String("file", actualDmlogFile))

	writeActualBlocks(actualJSONFile, actualBlocks)

	zlog.Info("blocks read, now comparing with reference")
	if jsonEq(expectedJSONFile, actualJSONFile) {
		fmt.Println("Files are equal, all good")
		os.Exit(0)
	}

	cmd := exec.Command("bash", "-c", fmt.Sprintf("diff -C 5 %s %s | less", expectedJSONFile, actualJSONFile))

	showDiff, wasAnswered := askQuestion(`File %q and %q differs, do you want to see the difference now`, expectedJSONFile, actualJSONFile)
	if wasAnswered && showDiff {
		cmd.Stdout = os.Stdout
		cmd.Stderr = os.Stderr

		noError(cmd.Run(), "Diff command failed to run properly")
	} else {
		fmt.Println("Not showing diff between files, run the following command to see it manually:")
		fmt.Println()
		fmt.Printf("    %s\n", makeSingleLineDiffCmd(cmd))
		fmt.Println("")
	}

	acceptDiff, wasAnswered := askQuestion(`Do you want to accept %q as the new %q right now`, actualJSONFile, expectedJSONFile)
	if wasAnswered && acceptDiff {
		inFile, err := os.Open(actualJSONFile)
		noError(err, "Unable to open actual file %q", actualJSONFile)
		defer inFile.Close()

		outFile, err := os.Create(expectedJSONFile)
		noError(err, "Unable to open epected file %q", expectedJSONFile)
		defer outFile.Close()

		_, err = io.Copy(outFile, inFile)
		noError(err, "Unable to copy file %q to %q", actualJSONFile, expectedJSONFile)

		err = compressFile(expectedJSONFile)
		noError(err, "Unable to compress file %q", expectedJSONFile)

		fmt.Printf("The file %q is now the new expected file\n", actualJSONFile)
	} else {
		fmt.Printf("You can make actual file %q the new expected file manually by doing:\n", actualJSONFile)
		fmt.Println("")
		fmt.Printf("    cp %s %s\n", actualJSONFile, expectedJSONFile)
		fmt.Printf("    zstd %s\n", expectedJSONFile)
		fmt.Println("")
	}

	os.Exit(1)
}

func makeSingleLineDiffCmd(cmd *exec.Cmd) string {
	return strings.Replace(strings.Replace(strings.Replace(cmd.String(), "diff -C", `"diff -C`, 1), "| less", `| less"`, 1), "\n", ", ", -1)
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
			out, err := jsonpb.MarshalIndentToString(block, "  ")
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

func readActualBlocks(filePath string) []*pbantelope.Block {
	blocks := []*pbantelope.Block{}

	file, err := os.Open(filePath)
	noError(err, "Unable to open actual blocks file %q", filePath)
	defer file.Close()

	lineChannel := make(chan string)
	consoleReader, err := codec.NewConsoleReader(lineChannel, firecore.NewGenericBlockEncoder(int32(pbbstream.Protocol_EOS)), zlog, tracer)
	if err != nil {
		zlog.Fatal("failed to init console reader", zap.Error(err))
	}

	go func() {
		err = consoleReader.ProcessData(file)
		if err != nil && err != io.EOF {
			zlog.Fatal("failed to process data", zap.Error(err))
		}
	}()

	var lastBlockRead *pbantelope.Block
	for {
		el, err := consoleReader.ReadBlock()

		if el != nil && el.ToProtocol().(*pbantelope.Block) != nil {
			block, ok := el.ToProtocol().(*pbantelope.Block)
			ensure(ok, `Read block is not a "pbantelope.Block" but should have been`)

			lastBlockRead = sanitizeBlock(block)
			blocks = append(blocks, lastBlockRead)
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

//func setupScanner(file io.Reader) error {
//	maxTokenSize := uint64(50 * 1024 * 1024)
//	if maxBufferSize := os.Getenv("MINDREADER_MAX_TOKEN_SIZE"); maxBufferSize != "" {
//		bs, err := strconv.ParseUint(maxBufferSize, 10, 64)
//		if err != nil {
//			zlog.Error("environment variable 'MINDREADER_MAX_TOKEN_SIZE' is set but invalid parse uint", zap.Error(err))
//		} else {
//			zlog.Info("setting max_token_size from environment variable MINDREADER_MAX_TOKEN_SIZE", zap.Uint64("max_token_size", bs))
//			maxTokenSize = bs
//		}
//	}
//	buf := make([]byte, maxTokenSize)
//	scanner := bufio.NewScanner(file)
//	scanner.Buffer(buf, len(buf))
//
//	lineChannel := make(chan string)
//
//	logger, tracer := logging.PackageLogger("battlefield", "github.com/pinax-network/leap-boot")
//
//	consoleReader, err := codec.NewConsoleReader(lineChannel, firecore.NewGenericBlockEncoder(int32(pbbstream.Protocol_EOS)), logger, tracer)
//	if err != nil {
//		return err
//	}
//
//	consoleReader.ProcessData()
//
//	go func() {
//		for scanner.Scan() {
//			line := scanner.Text()
//			if !strings.HasPrefix(line, "DMLOG ") {
//				continue
//			}
//			lineChannel <- line
//		}
//
//		err = scanner.Err()
//		if err != nil && err != io.EOF {
//			zlog.Error("console read line scanner encountered an error", zap.Error(err))
//		}
//
//		close(lineChannel)
//	}()
//}

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

func jsonEq(expectedFile string, actualFile string) bool {
	expected, err := ioutil.ReadFile(expectedFile)
	noError(err, "Unable to read %q", expectedFile)

	actual, err := ioutil.ReadFile(actualFile)
	noError(err, "Unable to read %q", actualFile)

	var expectedJSONAsInterface, actualJSONAsInterface interface{}

	err = json.Unmarshal(expected, &expectedJSONAsInterface)
	noError(err, "Expected file %q is not a valid JSON file", expectedFile)

	err = json.Unmarshal(actual, &actualJSONAsInterface)
	noError(err, "Actual file %q is not a valid JSON file", actualFile)

	return assert.ObjectsAreEqualValues(expectedJSONAsInterface, actualJSONAsInterface)
}

func askQuestion(label string, args ...interface{}) (answeredYes bool, wasAnswered bool) {
	if !terminal.IsTerminal(int(os.Stdout.Fd())) {
		zlog.Info("stdout is not a terminal, assuming no default")
		wasAnswered = false
		return
	}

	prompt := promptui.Prompt{
		Label:     dedent.Dedent(fmt.Sprintf(label, args...)),
		IsConfirm: true,
	}

	result, err := prompt.Run()
	if err != nil {
		zlog.Info("unable to aks user to see diff right now, too bad", zap.Error(err))
		wasAnswered = false
		return
	}

	wasAnswered = true
	answeredYes = strings.ToLower(result) == "y" || strings.ToLower(result) == "yes"
	return
}

func compressFile(file string) error {
	compressedFile := file + ".zst"
	encoder, _ := zstd.NewWriter(nil)

	content, err := ioutil.ReadFile(file)
	if err != nil {
		return fmt.Errorf("unable to read file %q: %w", file, err)
	}

	return os.WriteFile(compressedFile, encoder.EncodeAll(content, nil), os.ModePerm)
}

func uncompressFile(file string) error {
	compressedFile := file + ".zst"
	decoder, _ := zstd.NewReader(nil)

	content, err := ioutil.ReadFile(compressedFile)
	if err != nil {
		return fmt.Errorf("unable to read file %q: %w", compressedFile, err)
	}

	buf, err := decoder.DecodeAll(content, make([]byte, 0, len(content)))
	if err != nil {
		return fmt.Errorf("unable to decode file %q: %w", compressedFile, err)
	}

	return os.WriteFile(file, buf, os.ModePerm)
}

func fileExists(path string) bool {
	stat, err := os.Stat(path)
	if err != nil {
		// For this script, we don't care
		return false
	}

	return !stat.IsDir()
}

func ensure(condition bool, message string, args ...interface{}) {
	if !condition {
		quit(message, args...)
	}
}

func noError(err error, message string, args ...interface{}) {
	if err != nil {
		quit(message+": "+err.Error(), args...)
	}
}

func quit(message string, args ...interface{}) {
	fmt.Printf(message+"\n", args...)
	os.Exit(1)
}

func generateExpected(dmlogFile, expectedJsonFile string) {

	actualBlocks := readActualBlocks(dmlogFile)
	zlog.Info("read all blocks from dmlog file", zap.Int("block_count", len(actualBlocks)), zap.String("file", dmlogFile))

	writeActualBlocks(expectedJsonFile, actualBlocks)

	err := compressFile(expectedJsonFile)
	noError(err, "Unable to compress file %q", expectedJsonFile)
}

func blockReaderFactory(reader io.Reader) (bstream.BlockReader, error) {
	return bstream.NewDBinBlockReader(reader, func(contentType string, version int32) error {
		protocol := pbbstream.Protocol(pbbstream.Protocol_value[contentType])
		if protocol != pbbstream.Protocol_EOS && version != 1 {
			return fmt.Errorf("reader only knows about %s block kind at version 1, got %s at version %d", protocol, contentType, version)
		}

		return nil
	})
}

func blockWriterFactory(writer io.Writer) (bstream.BlockWriter, error) {
	return bstream.NewDBinBlockWriter(writer, pbbstream.Protocol_EOS.String(), 1)
}
